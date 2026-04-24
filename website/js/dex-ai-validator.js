/**
 * SOST DEX — AI Risk Guardian (Copilot Module)
 *
 * Validates intents and detects problems before the user confirms.
 * Produces warnings classified as INFO, WARNING, or BLOCKING.
 *
 * BLOCKING warnings prevent the form from being submitted.
 * WARNING/INFO warnings are shown but don't block.
 */

const SOSTAIValidator = (function () {
  'use strict';

  /**
   * Validate an intent and produce risk assessment.
   *
   * @param {object} intent - Parsed intent from SOSTIntentParser
   * @param {object} context - { positions, identity, deals }
   * @returns {object} { info: [], warnings: [], blocking: [] }
   */
  function validate(intent, context) {
    var info = [];
    var warnings = [];
    var blocking = [];

    if (!intent || !intent.action_type) {
      blocking.push('No action detected. Describe what you want to do.');
      return { info: info, warnings: warnings, blocking: blocking };
    }

    // ── Price checks ────────────────────────────────────────────

    if (intent.price_sost) {
      var price = parseFloat(intent.price_sost);
      if (isNaN(price) || price <= 0) {
        blocking.push('Price must be a positive number.');
      } else if (price < 0.001) {
        warnings.push('Price is very low (' + intent.price_sost + ' SOST). Is this correct?');
      } else if (price > 10000) {
        warnings.push('Price is very high (' + intent.price_sost + ' SOST). Double-check before sending.');
      }
    } else if (intent.action_type !== 'otc_request' && intent.action_type !== 'cancel') {
      warnings.push('No price specified. The form will need a price before sending.');
    }

    // ── Expiry checks ───────────────────────────────────────────

    if (intent.expiry_seconds) {
      if (intent.expiry_seconds < 300) {
        warnings.push('Expiry is very short (' + Math.floor(intent.expiry_seconds / 60) + ' min). The counterparty may not have time to respond.');
      } else if (intent.expiry_seconds > 7 * 86400) {
        info.push('Offer valid for ' + Math.floor(intent.expiry_seconds / 86400) + ' days. Long expiry is fine but consider market changes.');
      }
    }

    // ── Position checks ─────────────────────────────────────────

    if (intent.action_type.startsWith('sell') && !intent.position_id) {
      warnings.push('No position specified. Select a position to sell.');
    }

    if (intent.position_id && context && context.positions) {
      var position = context.positions.find(function (p) {
        return (p.id || p.position_id) === intent.position_id;
      });

      if (!position) {
        warnings.push('Position ' + intent.position_id + ' not found in your portfolio.');
      } else {
        // Check ownership
        if (intent.action_type.startsWith('sell') && context.identity) {
          var isOwner = position.owner === context.identity.sostAddress ||
                        position.principal_owner === context.identity.sostAddress;
          if (!isOwner) {
            blocking.push('You do not appear to own this position. Cannot sell what you don\'t own.');
          }
        }

        // Check status
        if (position.status !== 'ACTIVE') {
          if (position.status === 'MATURED') {
            warnings.push('Position is matured. Consider withdrawing instead of selling.');
          } else if (position.status === 'REDEEMED' || position.status === 'EXPIRED') {
            blocking.push('Position is ' + position.status + '. Cannot trade a closed position.');
          }
        }

        // Check reward-only feasibility
        if (intent.reward_only && position.reward_settled) {
          blocking.push('Rewards for this position are already settled. Nothing to sell.');
        }

        // Maturity proximity
        if (position.expiry_time) {
          var daysLeft = Math.ceil((position.expiry_time * 1000 - Date.now()) / 86400000);
          if (daysLeft < 3) {
            warnings.push('Position matures in ' + daysLeft + ' day(s). Buyer may not benefit from remaining rewards.');
          }
        }
      }
    }

    // ── Counterparty checks ─────────────────────────────────────

    if (intent.counterparty) {
      if (context && context.identity && intent.counterparty === context.identity.signingPublic) {
        blocking.push('Cannot trade with yourself.');
      }
    }

    // ── Action-specific checks ──────────────────────────────────

    if (intent.action_type === 'cancel' && !intent.position_id) {
      warnings.push('No target specified for cancellation. Which offer/deal to cancel?');
    }

    // ── General safety ──────────────────────────────────────────

    if (intent.warnings && intent.warnings.length > 0) {
      intent.warnings.forEach(function (w) {
        if (warnings.indexOf(w) < 0) warnings.push(w);
      });
    }

    if (intent.confidence < 30) {
      info.push('Low confidence (' + intent.confidence + '%). Providing more details will improve accuracy.');
    }

    return { info: info, warnings: warnings, blocking: blocking };
  }

  return {
    validate: validate
  };
})();
