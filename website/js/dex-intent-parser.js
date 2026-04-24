/**
 * SOST DEX — Intent Parser (AI Copilot Module)
 *
 * Parses natural language input into structured trade parameters.
 * This is the "brain" of the AI form assistant — it interprets what
 * the user wants to do and produces a structured intent object.
 *
 * RULES:
 *   - The parser ONLY interprets and fills fields
 *   - It does NOT sign, send, or execute anything
 *   - Ambiguous input produces warnings, not assumptions
 *   - The user always reviews before any action
 */

const SOSTIntentParser = (function () {
  'use strict';

  // ── Pattern Definitions ───────────────────────────────────────

  var ACTION_PATTERNS = [
    { pattern: /\b(sell|vend[eo]|vender)\b.*\b(full|complet[ao]|toda|entera|position|posici[oó]n)\b/i, action: 'sell_full' },
    { pattern: /\b(sell|vend[eo]|vender)\b.*\b(reward|recompensa|derecho)\b/i, action: 'sell_reward' },
    { pattern: /\b(buy|compr[ao]|comprar)\b.*\b(full|complet[ao]|toda|entera|position|posici[oó]n)\b/i, action: 'buy_full' },
    { pattern: /\b(buy|compr[ao]|comprar)\b.*\b(reward|recompensa|derecho)\b/i, action: 'buy_reward' },
    { pattern: /\b(sell|vend[eo]|vender)\b/i, action: 'sell_full' },
    { pattern: /\b(buy|compr[ao]|comprar)\b/i, action: 'buy_full' },
    { pattern: /\b(otc|request|quote|cotizaci[oó]n|pedir)\b/i, action: 'otc_request' },
    { pattern: /\b(cancel|cancelar|revok[ea]r)\b/i, action: 'cancel' }
  ];

  var PRICE_PATTERNS = [
    /(?:por|for|at|price|precio)\s*[:=]?\s*([0-9]+(?:\.[0-9]+)?)\s*(?:sost)?/i,
    /([0-9]+(?:\.[0-9]+)?)\s*sost/i,
    /\bprice\s+([0-9]+(?:\.[0-9]+)?)/i,
    /\bprecio\s+([0-9]+(?:\.[0-9]+)?)/i
  ];

  var EXPIRY_PATTERNS = [
    /(?:expir[eay]|caduc|expire?s?)\s*(?:en|in)?\s*([0-9]+)\s*(hour|hora|h|day|d[ií]a|min|minute|minuto)/i,
    /([0-9]+)\s*(hour|hora|h|day|d[ií]a)\s*(?:de\s*)?(?:expir|caduc|validez)/i
  ];

  var AMOUNT_PATTERNS = [
    /([0-9]+(?:\.[0-9]+)?)\s*(?:oz|onza|ounce|troy)/i,
    /\bamount\s*[:=]?\s*([0-9]+(?:\.[0-9]+)?)/i
  ];

  var POSITION_PATTERNS = [
    /\bpos(?:ition|ici[oó]n)?\s*(?:id)?\s*[:=]?\s*([a-f0-9]{8,16}|POS[-\w]+)/i,
    /\b(POS-\d{4}-\d{4}-\w+-\w+)/i
  ];

  var TOKEN_PATTERNS = [
    /\b(xaut|paxg)\b/i
  ];

  // ── Parser ────────────────────────────────────────────────────

  /**
   * Parse a natural language string into a structured intent.
   *
   * @param {string} input - User's natural language description
   * @param {object} context - Optional context: { positions, identity }
   * @returns {object} ParsedIntent
   */
  function parse(input, context) {
    var text = input.trim();
    if (!text) return _empty('No input provided');

    var intent = {
      action_type: null,
      position_id: null,
      offer_type: null,
      reward_only: false,
      token: null,
      amount_gold: null,
      price_sost: null,
      expiry_seconds: null,
      counterparty: null,
      otc_request_type: null,
      side: null,
      notes: null,
      warnings: [],
      confidence: 0,
      raw_input: text
    };

    // 1. Detect action
    for (var i = 0; i < ACTION_PATTERNS.length; i++) {
      if (ACTION_PATTERNS[i].pattern.test(text)) {
        intent.action_type = ACTION_PATTERNS[i].action;
        break;
      }
    }
    if (!intent.action_type) {
      intent.warnings.push('Could not determine action. Please specify: sell, buy, or otc.');
      return intent;
    }

    // Map action to offer_type and side
    switch (intent.action_type) {
      case 'sell_full':
        intent.offer_type = 'POSITION_FULL'; intent.side = 'sell'; intent.reward_only = false; break;
      case 'sell_reward':
        intent.offer_type = 'POSITION_REWARD_RIGHT'; intent.side = 'sell'; intent.reward_only = true; break;
      case 'buy_full':
        intent.offer_type = 'POSITION_FULL'; intent.side = 'buy'; intent.reward_only = false; break;
      case 'buy_reward':
        intent.offer_type = 'POSITION_REWARD_RIGHT'; intent.side = 'buy'; intent.reward_only = true; break;
      case 'otc_request':
        intent.offer_type = 'OTC'; intent.side = 'request'; break;
      case 'cancel':
        intent.offer_type = 'CANCEL'; break;
    }

    // 2. Extract price
    for (var p = 0; p < PRICE_PATTERNS.length; p++) {
      var pm = text.match(PRICE_PATTERNS[p]);
      if (pm) { intent.price_sost = pm[1]; break; }
    }

    // 3. Extract expiry
    for (var e = 0; e < EXPIRY_PATTERNS.length; e++) {
      var em = text.match(EXPIRY_PATTERNS[e]);
      if (em) {
        var val = parseInt(em[1]);
        var unit = em[2].toLowerCase();
        if (unit.startsWith('h')) intent.expiry_seconds = val * 3600;
        else if (unit.startsWith('d')) intent.expiry_seconds = val * 86400;
        else if (unit.startsWith('m')) intent.expiry_seconds = val * 60;
        break;
      }
    }

    // 4. Extract amount (gold oz)
    for (var a = 0; a < AMOUNT_PATTERNS.length; a++) {
      var am = text.match(AMOUNT_PATTERNS[a]);
      if (am) { intent.amount_gold = am[1]; break; }
    }

    // 5. Extract position ID
    for (var pi = 0; pi < POSITION_PATTERNS.length; pi++) {
      var pim = text.match(POSITION_PATTERNS[pi]);
      if (pim) { intent.position_id = pim[1]; break; }
    }

    // 6. Extract token
    var tokenMatch = text.match(TOKEN_PATTERNS[0]);
    if (tokenMatch) intent.token = tokenMatch[1].toUpperCase();

    // 7. Auto-fill from context
    if (context && context.positions && !intent.position_id) {
      var active = context.positions.filter(function (p) { return p.status === 'ACTIVE'; });
      if (active.length === 1) {
        intent.position_id = active[0].id || active[0].position_id;
        intent.notes = 'Auto-selected only active position: ' + intent.position_id;
      } else if (active.length > 1) {
        intent.warnings.push('Multiple active positions. Please specify which one.');
      }
    }

    // 8. Defaults
    if (!intent.expiry_seconds) intent.expiry_seconds = 86400; // 24h default
    if (!intent.token) intent.token = 'XAUT';

    // 9. Confidence score
    intent.confidence = _calcConfidence(intent);

    // 10. Validation warnings
    if (intent.price_sost && parseFloat(intent.price_sost) <= 0) {
      intent.warnings.push('Price is zero or negative.');
    }
    if (intent.action_type.startsWith('sell') && !intent.position_id) {
      intent.warnings.push('No position specified for sale.');
    }

    return intent;
  }

  function _calcConfidence(intent) {
    var score = 0;
    if (intent.action_type) score += 30;
    if (intent.position_id) score += 20;
    if (intent.price_sost) score += 20;
    if (intent.expiry_seconds) score += 10;
    if (intent.token) score += 10;
    if (intent.warnings.length === 0) score += 10;
    return Math.min(100, score);
  }

  function _empty(reason) {
    return {
      action_type: null, position_id: null, offer_type: null,
      reward_only: false, token: null, amount_gold: null,
      price_sost: null, expiry_seconds: null, counterparty: null,
      otc_request_type: null, side: null, notes: null,
      warnings: [reason], confidence: 0, raw_input: ''
    };
  }

  // ── OTC Intent Parser ────────────────────────────────────────

  /**
   * Parse OTC-specific intents.
   */
  function parseOTC(input) {
    var intent = parse(input);
    intent.action_type = 'otc_request';
    intent.offer_type = 'OTC';

    // Detect Model B
    if (/model\s*b|escrow/i.test(input)) {
      intent.otc_request_type = 'MODEL_B_ESCROW';
    } else if (/model\s*a|custody/i.test(input)) {
      intent.otc_request_type = 'MODEL_A_CUSTODY';
    }

    return intent;
  }

  return {
    parse: parse,
    parseOTC: parseOTC
  };
})();
