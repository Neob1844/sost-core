/* Tests for the DEX security-gate TOTP core against RFC 6238 SHA-1 test vectors.
   Proves the 2FA is a correct standard TOTP (interoperable with real authenticator apps),
   not decorative. Node 20 provides globalThis.crypto (webcrypto). */
var G = require("./dex-security-gate.js");
var pass = 0, fail = 0;
function ok(n, c) { if (c) pass++; else { fail++; console.log("  FAIL:", n); } }

// RFC 6238 SHA-1 shared secret = ASCII "12345678901234567890" -> base32:
var SECRET_ASCII = "12345678901234567890";
var secretBytes = new Uint8Array([].map.call(SECRET_ASCII, function (c) { return c.charCodeAt(0); }));
var SECRET_B32 = G.b32encode(secretBytes);

// base32 round-trip
ok("b32 round-trip", String(G.b32decode(SECRET_B32)) === String(secretBytes));
ok("b32 of RFC secret", SECRET_B32 === "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ");

(async function () {
  // RFC 6238 vectors (SHA-1), 6-digit truncation of the published 8-digit codes:
  //   T=59         -> 94287082 -> 287082
  //   T=1111111109 -> 07081804 -> 081804
  //   T=1234567890 -> 89005924 -> 005924
  //   T=2000000000 -> 69279037 -> 279037
  var vectors = [[59, "287082"], [1111111109, "081804"], [1234567890, "005924"], [2000000000, "279037"]];
  for (var i = 0; i < vectors.length; i++) {
    var t = vectors[i][0], want = vectors[i][1];
    var got = await G.totp(SECRET_B32, t, 30);
    ok("TOTP@" + t + " == " + want + " (got " + got + ")", got === want);
    // verifyAt accepts the exact code
    ok("verifyAt accepts @" + t, await G.verifyAt(SECRET_B32, want, t, 30));
  }
  // window tolerance: a code from the previous 30s step still verifies
  ok("±1 step window accepts prev code", await G.verifyAt(SECRET_B32, await G.totp(SECRET_B32, 1234567890 - 30, 30), 1234567890, 30));
  // a wrong / malformed code is rejected
  ok("rejects wrong code", !(await G.verifyAt(SECRET_B32, "000000", 59, 30)));
  ok("rejects non-6-digit", !(await G.verifyAt(SECRET_B32, "12345", 59, 30)));
  ok("rejects far-out-of-window code", !(await G.verifyAt(SECRET_B32, "287082", 1234567890, 30)));

  console.log("DEX-SECURITY-GATE TESTS: PASS=" + pass + " FAIL=" + fail);
  process.exit(fail ? 1 : 0);
})();
