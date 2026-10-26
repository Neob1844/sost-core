// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

/// @title Gold Access Key fee math (C701, development only)
/// @notice feeEUR  = min(50, max(0.50, bridgeValueEUR * 0.001))
///         feeXAUT = feeEUR / verifiedXAUTPriceEUR, rounded UP to the 6 decimals of XAUT.
///         Operations whose bridge value is below 100 EUR are rejected (never executed).
/// @dev    Integer math only. EUR amounts are scaled by 1e8 ("EUR8"). The bridge value is carried
///         as an exact rational vNum / vDen in EUR8 so that no intermediate rounding happens:
///         from a SOST amount, vNum = amountStocks * sostEur8 and vDen = 1e8 (stocks per SOST).
///         The single rounding step is the final ceiling to XAUT base units (1e-6 XAUT), which
///         always favours Gold Reserve V2 by less than one base unit.
library GoldAccessKey {
    uint256 internal constant EUR8 = 1e8;
    uint256 internal constant STOCKS_PER_SOST = 1e8;      // SOST and wSOST: 8 decimals
    uint256 internal constant XAUT_UNIT = 1e6;            // XAUT on Ethereum: 6 decimals (verified)
    uint256 internal constant FEE_MIN_EUR8 = 50_000_000;  // 0.50 EUR
    uint256 internal constant FEE_MAX_EUR8 = 25_000_000_000; // 250 EUR
    uint256 internal constant MIN_OPERATION_EUR8 = 10_000_000_000; // 100 EUR
    uint256 internal constant RATE_DEN = 1000;            // 0.10 % = 1 / 1000

    error BelowMinimumOperation();
    error ZeroPrice();
    error BadDenominator();

    /// @return true when the bridge value vNum/vDen (EUR8) reaches the 100 EUR operation minimum.
    function meetsMinimum(uint256 vNum, uint256 vDen) internal pure returns (bool) {
        if (vDen == 0) revert BadDenominator();
        return vNum >= MIN_OPERATION_EUR8 * vDen;
    }

    /// @notice Fee in XAUT base units (6 decimals), ceiling. Reverts below the operation minimum.
    /// @param vNum     bridge value numerator  (EUR8 units * vDen)
    /// @param vDen     bridge value denominator (> 0)
    /// @param xautEur8 verified XAUT price in EUR8 (EUR per 1 whole XAUT, scaled 1e8)
    function feeXaut(uint256 vNum, uint256 vDen, uint256 xautEur8) internal pure returns (uint256) {
        if (xautEur8 == 0) revert ZeroPrice();
        if (!meetsMinimum(vNum, vDen)) revert BelowMinimumOperation();
        // proportional fee in EUR8 = vNum / (vDen * 1000)
        uint256 num;
        uint256 den;
        if (vNum < FEE_MIN_EUR8 * RATE_DEN * vDen) {
            num = FEE_MIN_EUR8; den = 1;                 // floor of 0.50 EUR
        } else if (vNum > FEE_MAX_EUR8 * RATE_DEN * vDen) {
            num = FEE_MAX_EUR8; den = 1;                 // cap of 250 EUR
        } else {
            num = vNum; den = vDen * RATE_DEN;           // exact 0.10 %
        }
        // feeXAUT units = ceil( (num/den) EUR8 * 1e6 / xautEur8 )
        uint256 n = num * XAUT_UNIT;
        uint256 d = den * xautEur8;
        return (n + d - 1) / d;
    }

    /// @notice Fee in EUR8 for display (floor of the exact value; informational only).
    function feeEur8(uint256 vNum, uint256 vDen) internal pure returns (uint256) {
        if (vDen == 0) revert BadDenominator();
        if (vNum < FEE_MIN_EUR8 * RATE_DEN * vDen) return FEE_MIN_EUR8;
        if (vNum > FEE_MAX_EUR8 * RATE_DEN * vDen) return FEE_MAX_EUR8;
        return vNum / (vDen * RATE_DEN);
    }

    /// @notice Convenience for a SOST amount in stocks at a SOST/EUR price in EUR8.
    function feeXautForAmount(uint256 amountStocks, uint256 sostEur8, uint256 xautEur8) internal pure returns (uint256) {
        return feeXaut(amountStocks * sostEur8, STOCKS_PER_SOST, xautEur8);
    }
}
