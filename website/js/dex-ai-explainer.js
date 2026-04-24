/**
 * SOST DEX — AI Deal Explainer (Copilot Module)
 *
 * Explains in human language what a trade action does:
 * - What changes in SOST
 * - What changes in Ethereum
 * - What stays the same
 * - Full sale vs reward-only comparison
 */

const SOSTAIExplainer = (function () {
  'use strict';

  /**
   * Generate a human-readable explanation for an intent.
   */
  function explain(intent, context) {
    var lines = [];
    var position = _findPosition(intent.position_id, context);

    switch (intent.action_type) {
      case 'sell_full':
        lines.push('You are selling the ENTIRE position.');
        lines.push('');
        lines.push('What transfers to the buyer:');
        lines.push('  - Principal ownership (who owns the gold claim)');
        lines.push('  - Reward rights (who receives SOST mining rewards)');
        lines.push('  - Ethereum beneficiary (who can withdraw gold at maturity)');
        lines.push('');
        lines.push('What stays the same:');
        lines.push('  - The gold remains locked in escrow until maturity');
        lines.push('  - The escrow contract is immutable');
        if (position) {
          lines.push('  - Gold amount: ' + (position.amount_oz || '?') + ' oz ' + (position.token || 'XAUT'));
          if (position.expiry_time) {
            var days = Math.ceil((position.expiry_time * 1000 - Date.now()) / 86400000);
            lines.push('  - Time to maturity: ~' + days + ' days');
          }
        }
        lines.push('');
        lines.push('After this trade, you will have NO rights over this position.');
        break;

      case 'sell_reward':
        lines.push('You are selling ONLY the reward right.');
        lines.push('');
        lines.push('What transfers to the buyer:');
        lines.push('  - Reward rights (SOST mining rewards from this position)');
        lines.push('');
        lines.push('What you KEEP:');
        lines.push('  - Principal ownership');
        lines.push('  - Ethereum beneficiary (you still withdraw gold at maturity)');
        lines.push('');
        lines.push('This is like selling a "dividend stream" — the buyer gets the');
        lines.push('ongoing SOST rewards, but you keep the gold.');
        if (position && position.reward_total_sost) {
          var remaining = (position.reward_total_sost || 0) - (position.reward_claimed_sost || 0);
          lines.push('');
          lines.push('Estimated remaining reward: ~' + (remaining / 1e8).toFixed(2) + ' SOST');
        }
        break;

      case 'buy_full':
        lines.push('You are buying the ENTIRE position.');
        lines.push('');
        lines.push('What you receive:');
        lines.push('  - Principal ownership');
        lines.push('  - Reward rights');
        lines.push('  - Ethereum beneficiary (you can withdraw gold at maturity)');
        lines.push('');
        lines.push('You pay: ' + (intent.price_sost || '?') + ' SOST');
        break;

      case 'buy_reward':
        lines.push('You are buying ONLY the reward right.');
        lines.push('');
        lines.push('What you receive:');
        lines.push('  - SOST mining rewards from this position');
        lines.push('');
        lines.push('What you do NOT receive:');
        lines.push('  - Principal ownership');
        lines.push('  - Gold withdrawal rights');
        break;

      case 'otc_request':
        lines.push('You are requesting an OTC (over-the-counter) trade.');
        lines.push('This will be reviewed by the operator and may become a deal.');
        if (intent.otc_request_type === 'MODEL_B_ESCROW') {
          lines.push('Model B: Gold deposited in immutable Ethereum escrow.');
        }
        break;

      default:
        lines.push('Action: ' + (intent.action_type || 'unknown'));
    }

    // Price context
    if (intent.price_sost) {
      lines.push('');
      lines.push('Price: ' + intent.price_sost + ' SOST');
      lines.push('Expiry: ' + (intent.expiry_seconds ? Math.floor(intent.expiry_seconds / 3600) + ' hours' : '24 hours'));
    }

    return lines.join('\n');
  }

  /**
   * Compare full sale vs reward-only sale for a position.
   */
  function compareFullVsReward(position) {
    if (!position) return 'Position data needed for comparison.';

    var lines = [];
    lines.push('=== FULL POSITION SALE ===');
    lines.push('You give up: principal + rewards + gold withdrawal');
    lines.push('You receive: SOST payment (full price)');
    lines.push('After sale: no further rights');
    lines.push('');
    lines.push('=== REWARD-ONLY SALE ===');
    lines.push('You give up: only the SOST reward stream');
    lines.push('You keep: principal ownership + gold withdrawal');
    lines.push('You receive: SOST payment (typically lower than full sale)');
    lines.push('After sale: you still own the gold and can withdraw at maturity');
    lines.push('');
    lines.push('=== RECOMMENDATION ===');

    if (position.expiry_time) {
      var daysLeft = Math.ceil((position.expiry_time * 1000 - Date.now()) / 86400000);
      if (daysLeft < 7) {
        lines.push('Position matures in ' + daysLeft + ' days. Selling reward right');
        lines.push('may yield less because most rewards have already been earned.');
      } else if (daysLeft > 90) {
        lines.push('Position has ' + daysLeft + ' days until maturity. Reward-only sale');
        lines.push('could be attractive if you want to keep the gold long-term.');
      } else {
        lines.push('Both options are viable. Consider whether you want to keep');
        lines.push('the gold exposure or fully exit the position.');
      }
    }

    return lines.join('\n');
  }

  function _findPosition(posId, context) {
    if (!context || !context.positions || !posId) return null;
    return context.positions.find(function (p) {
      return (p.id || p.position_id) === posId;
    }) || null;
  }

  return {
    explain: explain,
    compareFullVsReward: compareFullVsReward
  };
})();
