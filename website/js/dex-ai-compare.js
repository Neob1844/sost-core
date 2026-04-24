/**
 * SOST DEX — AI Compare Helper (Copilot Module)
 *
 * Compares trade alternatives to help the user make informed decisions.
 * Answers questions like "should I sell full or reward-only?"
 */

const SOSTAICompare = (function () {
  'use strict';

  /**
   * Compare two trade options for a position.
   *
   * @param {object} position - Position data
   * @param {string} optionA - e.g. 'sell_full'
   * @param {string} optionB - e.g. 'sell_reward'
   * @returns {object} Comparison result
   */
  function compare(position, optionA, optionB) {
    if (!position) return { summary: 'Position data needed for comparison.', recommendation: null };

    var analyses = {};
    analyses[optionA] = _analyzeOption(position, optionA);
    analyses[optionB] = _analyzeOption(position, optionB);

    var recommendation = _recommend(position, optionA, optionB, analyses);

    return {
      optionA: { name: _label(optionA), analysis: analyses[optionA] },
      optionB: { name: _label(optionB), analysis: analyses[optionB] },
      recommendation: recommendation,
      summary: _buildSummary(analyses, optionA, optionB, recommendation)
    };
  }

  /**
   * Quick comparison: full sale vs reward-only.
   */
  function fullVsReward(position) {
    return compare(position, 'sell_full', 'sell_reward');
  }

  /**
   * Quick comparison: sell now vs hold to maturity.
   */
  function sellVsHold(position) {
    return compare(position, 'sell_full', 'hold');
  }

  function _analyzeOption(position, option) {
    var result = { youGive: [], youKeep: [], youReceive: [], risks: [] };

    switch (option) {
      case 'sell_full':
        result.youGive = ['Principal ownership', 'Reward rights', 'Gold withdrawal rights'];
        result.youKeep = [];
        result.youReceive = ['SOST payment (full position value)'];
        result.risks = ['No further rights after sale', 'Price may rise after selling'];
        break;
      case 'sell_reward':
        result.youGive = ['Reward rights (SOST stream)'];
        result.youKeep = ['Principal ownership', 'Gold withdrawal at maturity'];
        result.youReceive = ['SOST payment (reward value only)'];
        result.risks = ['Lower payment than full sale', 'Still exposed to gold price risk'];
        break;
      case 'hold':
        result.youGive = [];
        result.youKeep = ['Everything — principal, rewards, gold'];
        result.youReceive = ['Ongoing SOST rewards until maturity', 'Gold at maturity'];
        result.risks = ['Gold price may drop', 'SOST reward value may change', 'Liquidity locked'];
        break;
      case 'buy_full':
        result.youGive = ['SOST payment'];
        result.youKeep = [];
        result.youReceive = ['Principal ownership', 'Reward rights', 'Gold withdrawal'];
        result.risks = ['Gold price may drop', 'Reward stream may be partially claimed'];
        break;
      case 'buy_reward':
        result.youGive = ['SOST payment'];
        result.youKeep = [];
        result.youReceive = ['SOST reward stream only'];
        result.risks = ['No gold exposure', 'Reward may be small if near maturity'];
        break;
    }

    return result;
  }

  function _recommend(position, optA, optB, analyses) {
    if (!position || !position.expiry_time) return 'Insufficient data for recommendation.';

    var daysLeft = Math.ceil((position.expiry_time * 1000 - Date.now()) / 86400000);

    if (optA === 'sell_full' && optB === 'sell_reward') {
      if (daysLeft < 7) return 'Near maturity — reward-only sale may yield very little. Full sale recommended if you want to exit.';
      if (daysLeft > 180) return 'Long time to maturity — reward-only sale keeps gold exposure while generating SOST now.';
      return 'Both options are viable. Full sale for complete exit, reward-only to keep gold exposure.';
    }

    if (optA === 'sell_full' && optB === 'hold') {
      if (daysLeft < 7) return 'Very close to maturity — holding to withdraw gold may be better than selling.';
      return 'Selling now provides immediate SOST. Holding provides ongoing rewards + gold at maturity.';
    }

    return 'Review both options and choose based on your goals.';
  }

  function _buildSummary(analyses, optA, optB, recommendation) {
    var lines = [];
    lines.push('OPTION A: ' + _label(optA));
    lines.push('  Give: ' + (analyses[optA].youGive.join(', ') || 'nothing'));
    lines.push('  Keep: ' + (analyses[optA].youKeep.join(', ') || 'nothing'));
    lines.push('  Receive: ' + (analyses[optA].youReceive.join(', ') || 'nothing'));
    lines.push('');
    lines.push('OPTION B: ' + _label(optB));
    lines.push('  Give: ' + (analyses[optB].youGive.join(', ') || 'nothing'));
    lines.push('  Keep: ' + (analyses[optB].youKeep.join(', ') || 'nothing'));
    lines.push('  Receive: ' + (analyses[optB].youReceive.join(', ') || 'nothing'));
    lines.push('');
    lines.push('RECOMMENDATION: ' + recommendation);
    return lines.join('\n');
  }

  function _label(option) {
    var labels = {
      'sell_full': 'Sell Full Position',
      'sell_reward': 'Sell Reward Right Only',
      'buy_full': 'Buy Full Position',
      'buy_reward': 'Buy Reward Right',
      'hold': 'Hold Until Maturity'
    };
    return labels[option] || option;
  }

  return {
    compare: compare,
    fullVsReward: fullVsReward,
    sellVsHold: sellVsHold
  };
})();
