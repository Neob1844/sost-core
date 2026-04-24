/**
 * SOST DEX — AI Form Assistant
 *
 * Takes a parsed intent and fills the Trade Composer or OTC form.
 * Also provides the review layer ("What the assistant understood")
 * and human confirmation flow.
 *
 * HARD RULES:
 *   - Does NOT sign
 *   - Does NOT send
 *   - Does NOT execute settlement
 *   - Does NOT change beneficiary
 *   - Only interprets, fills, explains, and warns
 *   - User must explicitly confirm before any action
 */

const SOSTAIAssistant = (function () {
  'use strict';

  /**
   * Process user input and produce a complete assistant response.
   *
   * @param {string} input - Natural language from the user
   * @param {object} context - { positions, identity, deals }
   * @returns {object} AssistantResponse
   */
  function process(input, context) {
    var intent = SOSTIntentParser.parse(input, context);

    // Build the review summary
    var review = buildReview(intent, context);

    // Run risk checks
    var risks = SOSTAIValidator.validate(intent, context);

    // Generate explanation
    var explanation = SOSTAIExplainer.explain(intent, context);

    return {
      intent: intent,
      review: review,
      risks: risks,
      explanation: explanation,
      confidence: intent.confidence,
      canProceed: risks.blocking.length === 0 && intent.confidence >= 30,
      assistantNote: _buildNote(intent, risks)
    };
  }

  /**
   * Process OTC-specific input.
   */
  function processOTC(input, context) {
    var intent = SOSTIntentParser.parseOTC(input, context);
    var review = buildReview(intent, context);
    var risks = SOSTAIValidator.validate(intent, context);

    return {
      intent: intent,
      review: review,
      risks: risks,
      confidence: intent.confidence,
      canProceed: risks.blocking.length === 0,
      assistantNote: _buildNote(intent, risks)
    };
  }

  /**
   * Build the "What the assistant understood" review object.
   */
  function buildReview(intent, context) {
    var review = {
      action: _actionLabel(intent.action_type),
      position: intent.position_id || '(not specified)',
      token: intent.token || 'XAUT',
      amount_gold: intent.amount_gold || '(from position)',
      price: intent.price_sost ? intent.price_sost + ' SOST' : '(not specified)',
      expiry: _expiryLabel(intent.expiry_seconds),
      side: intent.side || '—',
      reward_only: intent.reward_only,
      counterparty: intent.counterparty || '(open market / operator-assisted)',
      changes_sost: [],
      changes_eth: [],
      unchanged: [],
      warnings: intent.warnings.slice()
    };

    // Position context
    var position = null;
    if (context && context.positions && intent.position_id) {
      position = context.positions.find(function (p) {
        return (p.id || p.position_id) === intent.position_id;
      });
    }

    if (intent.action_type === 'sell_full' || intent.action_type === 'buy_full') {
      review.changes_sost.push('principal_owner transfers to buyer');
      review.changes_sost.push('reward_owner transfers to buyer');
      review.changes_eth.push('eth_beneficiary updates to buyer ETH address');
      review.unchanged.push('Escrow remains locked until maturity');
      if (position) review.unchanged.push('Gold amount: ' + (position.amount_oz || '?') + ' oz');
    } else if (intent.action_type === 'sell_reward' || intent.action_type === 'buy_reward') {
      review.changes_sost.push('reward_owner transfers to buyer');
      review.unchanged.push('principal_owner remains unchanged');
      review.unchanged.push('eth_beneficiary remains unchanged');
      review.unchanged.push('Escrow remains locked until maturity');
    }

    return review;
  }

  /**
   * Apply the parsed intent to the Trade Composer form fields.
   * Returns a map of field_id → value to set.
   */
  function fillForm(intent) {
    var fields = {};

    // Action selection
    if (intent.action_type === 'sell_full') fields['_action'] = 'sell_full';
    else if (intent.action_type === 'sell_reward') fields['_action'] = 'sell_reward';
    else if (intent.action_type === 'buy_full') fields['_action'] = 'buy_full';
    else if (intent.action_type === 'buy_reward') fields['_action'] = 'buy_reward';
    else if (intent.action_type === 'otc_request') fields['_action'] = 'otc';

    // Position
    if (intent.position_id) fields['composerPositionCustom'] = intent.position_id;

    // Parameters
    if (intent.price_sost) fields['paramPrice'] = intent.price_sost;
    if (intent.amount_gold) fields['paramAmountGold'] = intent.amount_gold;
    if (intent.expiry_seconds) fields['paramExpiry'] = String(intent.expiry_seconds);

    // Asset type
    if (intent.reward_only) fields['paramAssetType'] = 'POSITION_REWARD_RIGHT';
    else if (intent.offer_type === 'POSITION_FULL') fields['paramAssetType'] = 'POSITION_FULL';

    // Token/pair
    if (intent.token === 'PAXG') fields['paramPair'] = 'SOST/PAXG';
    else fields['paramPair'] = 'SOST/XAUT';

    return fields;
  }

  // ── Helpers ───────────────────────────────────────────────────

  function _actionLabel(action) {
    var labels = {
      'sell_full': 'Sell full position',
      'sell_reward': 'Sell reward right only',
      'buy_full': 'Buy full position',
      'buy_reward': 'Buy reward right only',
      'otc_request': 'OTC request',
      'cancel': 'Cancel existing offer/deal'
    };
    return labels[action] || action || '(unknown)';
  }

  function _expiryLabel(seconds) {
    if (!seconds) return '24 hours (default)';
    if (seconds < 3600) return Math.floor(seconds / 60) + ' minutes';
    if (seconds < 86400) return Math.floor(seconds / 3600) + ' hours';
    return Math.floor(seconds / 86400) + ' days';
  }

  function _buildNote(intent, risks) {
    if (risks.blocking.length > 0) {
      return 'Cannot proceed: ' + risks.blocking[0];
    }
    if (intent.confidence < 30) {
      return 'Low confidence — please provide more details.';
    }
    if (intent.warnings.length > 0) {
      return 'Ready with warnings. Please review before confirming.';
    }
    return 'Ready. Review the details and confirm when ready.';
  }

  return {
    process: process,
    processOTC: processOTC,
    buildReview: buildReview,
    fillForm: fillForm
  };
})();
