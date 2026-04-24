/**
 * SOST DEX — AI Lifecycle Guide (Copilot Module)
 *
 * Explains position lifecycle state and what actions are available.
 * Helps the user understand maturity, withdraw, reward, and beneficiary status.
 */

const SOSTAILifecycle = (function () {
  'use strict';

  /**
   * Analyze a position and produce a lifecycle summary.
   *
   * @param {object} position - Position data from positions_live.json
   * @returns {object} LifecycleSummary
   */
  function analyze(position) {
    if (!position) return { stage: 'unknown', summary: 'No position data available.', actions: [], warnings: [] };

    var now = Date.now();
    var summary = [];
    var actions = [];
    var warnings = [];
    var stage = position.lifecycle_status || position.status || 'UNKNOWN';

    // Time calculations
    var startTime = position.start_time ? position.start_time * 1000 : 0;
    var expiryTime = position.expiry_time ? position.expiry_time * 1000 : 0;
    var daysTotal = expiryTime && startTime ? Math.ceil((expiryTime - startTime) / 86400000) : 0;
    var daysLeft = expiryTime ? Math.ceil((expiryTime - now) / 86400000) : 0;
    var daysElapsed = daysTotal - daysLeft;
    var pctComplete = daysTotal > 0 ? Math.min(100, Math.round((daysElapsed / daysTotal) * 100)) : 0;

    // Stage analysis
    switch (stage.toUpperCase()) {
      case 'ACTIVE':
        summary.push('Position is ACTIVE and earning rewards.');
        summary.push('Progress: ' + pctComplete + '% complete (' + daysElapsed + '/' + daysTotal + ' days).');
        if (daysLeft > 0) summary.push('Maturity in: ' + daysLeft + ' days.');
        actions.push('Sell full position');
        actions.push('Sell reward right only');
        actions.push('Hold until maturity');
        if (daysLeft < 7) warnings.push('Position nearing maturity — selling reward right may yield less.');
        break;

      case 'NEARING_MATURITY':
        summary.push('Position is NEARING MATURITY.');
        summary.push(daysLeft + ' days remaining.');
        actions.push('Wait for maturity and withdraw');
        actions.push('Sell full position (time-sensitive)');
        warnings.push('Less than 7 days until maturity. Buyer options may be limited.');
        break;

      case 'MATURED':
        summary.push('Position has MATURED. Gold can be withdrawn.');
        actions.push('Withdraw gold from escrow');
        actions.push('Claim remaining rewards');
        if (!position.withdraw_tx) warnings.push('Withdrawal not yet executed.');
        break;

      case 'WITHDRAW_PENDING':
        summary.push('Withdrawal is PENDING. Transaction submitted.');
        actions.push('Wait for confirmation');
        break;

      case 'WITHDRAWN':
        summary.push('Gold has been WITHDRAWN from escrow.');
        if (!position.reward_settled) {
          actions.push('Settle remaining rewards');
          warnings.push('Rewards not yet settled.');
        } else {
          summary.push('Rewards are settled. Lifecycle nearly complete.');
        }
        break;

      case 'REWARD_SETTLED':
        summary.push('All rewards have been SETTLED.');
        if (position.withdraw_tx) {
          summary.push('Gold withdrawn. Lifecycle COMPLETE.');
        } else {
          actions.push('Withdraw gold from escrow');
          warnings.push('Rewards settled but gold not yet withdrawn.');
        }
        break;

      case 'CLOSED':
        summary.push('Position lifecycle is CLOSED. All operations complete.');
        break;

      default:
        summary.push('Status: ' + stage);
    }

    // Ownership info
    if (position.principal_owner && position.reward_owner) {
      var sameOwner = position.principal_owner === position.reward_owner;
      if (sameOwner) {
        summary.push('Ownership: unified (principal + reward = same owner).');
      } else {
        summary.push('Ownership: SPLIT — principal and reward have different owners.');
        summary.push('  Principal: ' + _short(position.principal_owner));
        summary.push('  Reward: ' + _short(position.reward_owner));
      }
    }

    // Beneficiary sync
    if (position.eth_beneficiary) {
      summary.push('ETH beneficiary: ' + _short(position.eth_beneficiary));
    }

    // Reward progress
    if (position.reward_total_sost) {
      var claimed = position.reward_claimed_sost || 0;
      var total = position.reward_total_sost;
      var rewardPct = Math.round((claimed / total) * 100);
      summary.push('Rewards: ' + rewardPct + '% claimed (' + (claimed / 1e8).toFixed(2) + ' / ' + (total / 1e8).toFixed(2) + ' SOST).');
    }

    return {
      stage: stage,
      summary: summary.join('\n'),
      actions: actions,
      warnings: warnings,
      daysLeft: daysLeft,
      pctComplete: pctComplete,
      isComplete: stage === 'CLOSED'
    };
  }

  function _short(addr) {
    if (!addr || addr.length < 12) return addr || '(none)';
    return addr.substring(0, 8) + '...' + addr.substring(addr.length - 4);
  }

  return {
    analyze: analyze
  };
})();
