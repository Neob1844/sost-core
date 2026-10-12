/* SOST — Tokenization Industry Comparison dataset. Sourced, honest, rubric-based. */
window.SOST_TOKCMP={
 "version": "2026-09-29",
 "verifiedAt": "2026-09-29",
 "order": [
  "sost",
  "securitize",
  "tokeny",
  "centrifuge",
  "polymesh",
  "mattereum",
  "inx"
 ],
 "platforms": [
  {
   "key": "sost",
   "name": "SOST",
   "focus": "Verifiable asset/project infrastructure",
   "model": "Own PoW Layer 1",
   "maturity": "Registry live · offerings gated",
   "diff": "Typed claims, per-claim provenance & deterministic Passport hash, four offering engines from one Passport",
   "sources": [
    [
     "Asset Registry v2 — live",
     "https://sostcore.com/sost-universal-assets.html"
    ]
   ]
  },
  {
   "key": "securitize",
   "name": "Securitize",
   "focus": "Regulated capital markets",
   "model": "Issues on public chains (no own L1)",
   "maturity": "Live, SEC/FINRA-registered",
   "diff": "Vertically integrated SEC-registered transfer agent · broker-dealer · ATS · fund admin · FINRA-approved custody",
   "sources": [
    [
     "Securitize 2Q26 8-K (SEC EDGAR)",
     "https://www.sec.gov/Archives/edgar/data/0002094496/000162828026056164/exhibit991-secz2q26earning.htm"
    ],
    [
     "Anchorage acquires Securitize Advisors",
     "https://www.anchorage.com/insights/anchorage-digital-acquires-securitize-advisors-platform-strengthen-wealth-management-platform"
    ]
   ]
  },
  {
   "key": "tokeny",
   "name": "Tokeny",
   "focus": "Compliance infrastructure",
   "model": "EVM (ERC-3643 / ONCHAINID)",
   "maturity": "Live standard, widely adopted",
   "diff": "ERC-3643 (T-REX): on-chain identity, protocol-level transfer compliance, agent-controlled freeze/forced-transfer/recovery",
   "sources": [
    [
     "ERC-3643 (EIP)",
     "https://eips.ethereum.org/EIPS/eip-3643"
    ],
    [
     "T-REX whitepaper (Tokeny)",
     "https://tokeny.com/wp-content/uploads/2023/05/ERC3643-Whitepaper-T-REX-v4.pdf"
    ],
    [
     "ERC3643 compliance docs",
     "https://docs.erc3643.org/erc-3643/smart-contracts-library/compliance-management"
    ]
   ]
  },
  {
   "key": "centrifuge",
   "name": "Centrifuge",
   "focus": "Institutional RWA finance",
   "model": "On-chain asset management infra (multichain)",
   "maturity": "Live, market leader in private credit",
   "diff": "Tokenized funds, treasuries & private credit with native DeFi lending/distribution",
   "sources": [
    [
     "Centrifuge — onchain asset management",
     "https://centrifuge.io/"
    ],
    [
     "Centrifuge RWA market",
     "https://centrifuge.io/rwa-market"
    ]
   ]
  },
  {
   "key": "polymesh",
   "name": "Polymesh",
   "focus": "Regulated-assets blockchain",
   "model": "Purpose-built permissioned Layer 1",
   "maturity": "Live L1",
   "diff": "Identity, native fungible/NFT assets, compliance, settlement & confidentiality as protocol primitives",
   "sources": [
    [
     "Polymesh — purpose-built L1 for RWAs",
     "https://polymesh.network/about-polymesh"
    ],
    [
     "Polymesh developer docs — identity",
     "https://developers.polymesh.network/introduction/identity"
    ]
   ]
  },
  {
   "key": "mattereum",
   "name": "Mattereum",
   "focus": "Legal asset linkage",
   "model": "EVM NFTs + legal protocol",
   "maturity": "Live protocol",
   "diff": "Asset Passport = bundle of legal warranties + expert certification with financial stake, arbitration in 170 countries",
   "sources": [
    [
     "Mattereum — how it works",
     "https://mattereum.com/how-it-works/"
    ],
    [
     "Mattereum — services",
     "https://mattereum.com/services/"
    ]
   ]
  },
  {
   "key": "inx",
   "name": "INX / Republic",
   "focus": "Regulated marketplace",
   "model": "US-regulated venue (no own L1)",
   "maturity": "Live, Republic-owned",
   "diff": "US broker-dealer + transfer agent + ATS for 24/7 secondary trading of security tokens",
   "sources": [
    [
     "Republic acquires INX ($60M)",
     "https://techstartups.com/2025/04/03/republic-acquires-inx-for-60m-to-build-regulated-global-platform-for-tokenized-assets/"
    ],
    [
     "INX ATS for security-token listings",
     "https://www.marketsmedia.com/inx-ats-prepared-for-securities-token-listings/"
    ]
   ]
  }
 ],
 "dimensions": [
  {
   "cat": "asset",
   "label": "Asset Passport / digital twin",
   "exec": true,
   "cells": {
    "sost": [
     5,
     "C",
     "Asset Passport v2 seals asset, right, evidence and valuation into one verifiable record"
    ],
    "securitize": [
     2,
     "",
     "Issuance/records infrastructure, not an evidence-passport product"
    ],
    "tokeny": [
     1,
     "",
     "Token + identity focus; no asset-evidence passport layer"
    ],
    "centrifuge": [
     1,
     "",
     "Asset modelled as a financing pool, not an evidence passport"
    ],
    "polymesh": [
     2,
     "",
     "Native asset object on-chain, but not an evidence/warranty passport"
    ],
    "mattereum": [
     5,
     "C",
     "Mattereum Asset Passport is the core product — a legal digital twin of the physical object"
    ],
    "inx": [
     1,
     "",
     "Marketplace/venue; assets come from issuers, no native passport"
    ]
   }
  },
  {
   "cat": "asset",
   "label": "Evidence capture",
   "exec": true,
   "cells": {
    "sost": [
     5,
     "C",
     "Captures documents/photos/attestations as first-class evidence behind each claim"
    ],
    "securitize": [
     3,
     "",
     "Collects offering/issuer documentation as part of regulated onboarding"
    ],
    "tokeny": [
     2,
     "",
     "Identity claims captured via ONCHAINID; asset evidence out of scope"
    ],
    "centrifuge": [
     2,
     "",
     "Loan/pool documentation captured for credit assessment"
    ],
    "polymesh": [
     2,
     "",
     "Documents referenced at issuance; not an evidence engine"
    ],
    "mattereum": [
     4,
     "C",
     "Expert certifications and documents attached, backed by warranties"
    ],
    "inx": [
     2,
     "",
     "Issuer discloses documents for listing/compliance"
    ]
   }
  },
  {
   "cat": "asset",
   "label": "Per-claim provenance",
   "exec": true,
   "cells": {
    "sost": [
     5,
     "C",
     "Every material assertion carries WHO-says-it, SOURCE and verification state (Claims v2)"
    ],
    "securitize": [
     2,
     "",
     "Provenance handled off-chain in regulated records, not per-claim on record"
    ],
    "tokeny": [
     2,
     "",
     "Provenance is identity-of-holder, not per-claim about the asset"
    ],
    "centrifuge": [
     1,
     "",
     "No per-claim provenance model"
    ],
    "polymesh": [
     2,
     "",
     "Attestations tied to identities, not a per-claim provenance graph"
    ],
    "mattereum": [
     3,
     "",
     "Warranties attributed to named experts, but not a typed per-claim graph"
    ],
    "inx": [
     1,
     "",
     "No per-claim provenance model"
    ]
   }
  },
  {
   "cat": "asset",
   "label": "Document hashing / integrity",
   "exec": false,
   "cells": {
    "sost": [
     5,
     "C",
     "SHA-256 file_hash + deterministic manifestHash anchor integrity on-chain"
    ],
    "securitize": [
     2,
     "",
     "Integrity kept in regulated systems of record"
    ],
    "tokeny": [
     3,
     "",
     "Token/identity state on-chain; document hashing app-specific"
    ],
    "centrifuge": [
     2,
     "",
     "Pool metadata on-chain; document hashing app-specific"
    ],
    "polymesh": [
     3,
     "",
     "On-chain asset docs referenced; hashing per issuer"
    ],
    "mattereum": [
     4,
     "C",
     "Passport documents hashed and bound to the NFT"
    ],
    "inx": [
     1,
     "",
     "Not a document-integrity layer"
    ]
   }
  },
  {
   "cat": "asset",
   "label": "Verification status per claim",
   "exec": false,
   "cells": {
    "sost": [
     5,
     "C",
     "Each claim is explicitly VERIFIED / SELF-DECLARED / UNVERIFIED"
    ],
    "securitize": [
     3,
     "",
     "Issuer/investor status verified in regulated flow"
    ],
    "tokeny": [
     3,
     "",
     "Holder eligibility verified via identity claims"
    ],
    "centrifuge": [
     2,
     "",
     "Credit verified by underwriters off-chain"
    ],
    "polymesh": [
     3,
     "",
     "Identity/claims verified on-chain"
    ],
    "mattereum": [
     4,
     "C",
     "Warranty truth backed by financial penalty = strong verification incentive"
    ],
    "inx": [
     2,
     "",
     "Investor verified for trading eligibility"
    ]
   }
  },
  {
   "cat": "asset",
   "label": "Tamper detection",
   "exec": false,
   "cells": {
    "sost": [
     5,
     "C",
     "Any change breaks manifestHash — third parties recompute and get MATCH/FAIL"
    ],
    "securitize": [
     2,
     "",
     "Records controlled by regulated registrar"
    ],
    "tokeny": [
     3,
     "",
     "On-chain token state is tamper-evident"
    ],
    "centrifuge": [
     2,
     "",
     "On-chain pool state tamper-evident"
    ],
    "polymesh": [
     3,
     "",
     "On-chain asset state tamper-evident"
    ],
    "mattereum": [
     4,
     "C",
     "NFT + hashed passport is tamper-evident"
    ],
    "inx": [
     2,
     "",
     "Trade records in regulated systems"
    ]
   }
  },
  {
   "cat": "asset",
   "label": "Reproducible / canonical record",
   "exec": false,
   "cells": {
    "sost": [
     5,
     "C",
     "RFC-8785-lite canonical JSON → anyone recomputes the exact hash"
    ],
    "securitize": [
     1,
     "",
     "No public canonical-record scheme"
    ],
    "tokeny": [
     3,
     "",
     "Deterministic on-chain token state"
    ],
    "centrifuge": [
     2,
     "",
     "Deterministic pool state"
    ],
    "polymesh": [
     3,
     "",
     "Deterministic native-asset state"
    ],
    "mattereum": [
     2,
     "",
     "Passport public but no canonical-hash recompute scheme published"
    ],
    "inx": [
     1,
     "",
     "No public canonical-record scheme"
    ]
   }
  },
  {
   "cat": "asset",
   "label": "Physical-asset support",
   "exec": false,
   "cells": {
    "sost": [
     4,
     "C",
     "Any class incl. physical (mining, real estate, vehicles) as evidence records"
    ],
    "securitize": [
     2,
     "",
     "Focus on financial securities"
    ],
    "tokeny": [
     2,
     "",
     "Any asset representable as ERC-3643, physical linkage app-side"
    ],
    "centrifuge": [
     3,
     "",
     "Real-world credit/assets financed"
    ],
    "polymesh": [
     3,
     "",
     "Any regulated asset; physical linkage app-side"
    ],
    "mattereum": [
     5,
     "C",
     "Physical assets are the entire point — legally bound twins"
    ],
    "inx": [
     2,
     "",
     "Whatever issuers list"
    ]
   }
  },
  {
   "cat": "asset",
   "label": "Project-before-asset support",
   "exec": false,
   "cells": {
    "sost": [
     5,
     "C",
     "Project Passport funds something not yet built, then becomes an Asset Passport"
    ],
    "securitize": [
     2,
     "",
     "Can raise for a fund/entity, not a project→asset lifecycle model"
    ],
    "tokeny": [
     0,
     "",
     "Not offered"
    ],
    "centrifuge": [
     3,
     "",
     "Finances originations/projects via pools"
    ],
    "polymesh": [
     1,
     "",
     "Not a project-lifecycle model"
    ],
    "mattereum": [
     0,
     "",
     "Not offered"
    ],
    "inx": [
     2,
     "",
     "Primary raises, not a project→asset lifecycle"
    ]
   }
  },
  {
   "cat": "token",
   "label": "Fractionalization",
   "exec": true,
   "cells": {
    "sost": [
     3,
     "G",
     "Rights divided into units in the Passport/offering layer (native units gated)"
    ],
    "securitize": [
     5,
     "C",
     "Fractional regulated securities issued and serviced"
    ],
    "tokeny": [
     5,
     "C",
     "Fractional permissioned tokens via ERC-3643"
    ],
    "centrifuge": [
     5,
     "C",
     "Fractional pool tokens"
    ],
    "polymesh": [
     5,
     "C",
     "Native fractional assets at protocol level"
    ],
    "mattereum": [
     4,
     "C",
     "Fractional ownership via rwaNFT structures"
    ],
    "inx": [
     4,
     "C",
     "Fractional security tokens traded"
    ]
   }
  },
  {
   "cat": "token",
   "label": "Token issuance",
   "exec": true,
   "cells": {
    "sost": [
     2,
     "G",
     "Modelled today; native issuance is a future protocol module"
    ],
    "securitize": [
     5,
     "C",
     "Regulated token issuance is the core business"
    ],
    "tokeny": [
     5,
     "C",
     "ERC-3643 issuance widely used"
    ],
    "centrifuge": [
     4,
     "C",
     "Issues pool/fund tokens"
    ],
    "polymesh": [
     5,
     "C",
     "Native asset issuance in-protocol"
    ],
    "mattereum": [
     3,
     "C",
     "Issues rwaNFTs"
    ],
    "inx": [
     3,
     "C",
     "Facilitates issuance for its marketplace"
    ]
   }
  },
  {
   "cat": "token",
   "label": "Native on-chain asset issuance",
   "exec": true,
   "cells": {
    "sost": [
     0,
     "F",
     "SOST native UTXO assets are a future gated module — not active"
    ],
    "securitize": [
     2,
     "",
     "Tokens live on external chains, not a native-asset L1"
    ],
    "tokeny": [
     3,
     "",
     "ERC-3643 tokens are EVM contracts, not L1-native assets"
    ],
    "centrifuge": [
     3,
     "",
     "Tokens on Centrifuge/EVM chains"
    ],
    "polymesh": [
     5,
     "C",
     "Assets are native first-class L1 objects"
    ],
    "mattereum": [
     2,
     "",
     "EVM NFTs, not native L1 assets"
    ],
    "inx": [
     1,
     "",
     "No native issuance layer"
    ]
   }
  },
  {
   "cat": "token",
   "label": "Supply controls",
   "exec": false,
   "cells": {
    "sost": [
     3,
     "G",
     "Supply defined in offering model; enforcement gated"
    ],
    "securitize": [
     5,
     "C",
     "Cap-table-grade supply control"
    ],
    "tokeny": [
     5,
     "C",
     "Agent-controlled supply per ERC-3643"
    ],
    "centrifuge": [
     4,
     "C",
     "Pool supply managed"
    ],
    "polymesh": [
     5,
     "C",
     "Protocol-level supply controls"
    ],
    "mattereum": [
     3,
     "C",
     "Per-asset NFT supply"
    ],
    "inx": [
     3,
     "C",
     "Issuer-defined supply"
    ]
   }
  },
  {
   "cat": "token",
   "label": "Mint / burn",
   "exec": false,
   "cells": {
    "sost": [
     2,
     "G",
     "Modelled in offering lifecycle; native mint/burn future"
    ],
    "securitize": [
     5,
     "C",
     "Full mint/burn under regulated control"
    ],
    "tokeny": [
     5,
     "C",
     "Mint/burn with compliance checks"
    ],
    "centrifuge": [
     4,
     "C",
     "Mint/burn of pool tokens"
    ],
    "polymesh": [
     5,
     "C",
     "Native mint/burn"
    ],
    "mattereum": [
     3,
     "C",
     "Mint/burn of asset NFTs"
    ],
    "inx": [
     2,
     "",
     "Handled by issuers"
    ]
   }
  },
  {
   "cat": "token",
   "label": "Transfer controls",
   "exec": true,
   "cells": {
    "sost": [
     2,
     "G",
     "Transfer rules modelled; on-chain enforcement is future"
    ],
    "securitize": [
     5,
     "C",
     "Regulated transfer restrictions enforced"
    ],
    "tokeny": [
     5,
     "C",
     "Protocol-level transfer compliance is the ERC-3643 headline"
    ],
    "centrifuge": [
     3,
     "",
     "Transfers within DeFi permissioning"
    ],
    "polymesh": [
     5,
     "C",
     "Compliance-gated transfers in-protocol"
    ],
    "mattereum": [
     2,
     "",
     "Transfer via NFT marketplace rules"
    ],
    "inx": [
     4,
     "C",
     "Transfers restricted to eligible investors on the ATS"
    ]
   }
  },
  {
   "cat": "token",
   "label": "Token lifecycle mgmt",
   "exec": false,
   "cells": {
    "sost": [
     3,
     "G",
     "Offering lifecycle + event log; native token lifecycle future"
    ],
    "securitize": [
     5,
     "C",
     "End-to-end regulated lifecycle + servicing"
    ],
    "tokeny": [
     5,
     "C",
     "Lifecycle incl. freeze/recovery via agent role"
    ],
    "centrifuge": [
     4,
     "C",
     "Fund/pool lifecycle"
    ],
    "polymesh": [
     5,
     "C",
     "Lifecycle primitives in-protocol"
    ],
    "mattereum": [
     3,
     "C",
     "Asset lifecycle via passport updates"
    ],
    "inx": [
     3,
     "C",
     "Lifecycle around trading"
    ]
   }
  },
  {
   "cat": "compliance",
   "label": "Legal-right definition",
   "exec": true,
   "cells": {
    "sost": [
     4,
     "C",
     "Right a token represents is explicitly typed; legal meaning NOT determined by SOST"
    ],
    "securitize": [
     4,
     "C",
     "Rights defined within regulated securities framework"
    ],
    "tokeny": [
     3,
     "",
     "Right encoded in token terms + compliance rules"
    ],
    "centrifuge": [
     3,
     "",
     "Rights defined per financing structure"
    ],
    "polymesh": [
     3,
     "",
     "Rights defined per asset"
    ],
    "mattereum": [
     5,
     "C",
     "Legal right defined + warranted + arbitration-enforceable"
    ],
    "inx": [
     3,
     "",
     "Rights per listed security"
    ]
   }
  },
  {
   "cat": "compliance",
   "label": "Legal enforceability layer",
   "exec": true,
   "cells": {
    "sost": [
     1,
     "",
     "SOST proves record integrity, explicitly NOT legal enforceability"
    ],
    "securitize": [
     5,
     "C",
     "Enforceable via SEC-registered entities + legal agreements"
    ],
    "tokeny": [
     3,
     "",
     "Enforceability via issuer legal wrapper"
    ],
    "centrifuge": [
     3,
     "",
     "Enforceability via fund/legal structure"
    ],
    "polymesh": [
     3,
     "",
     "Regulated framework around the L1"
    ],
    "mattereum": [
     5,
     "C",
     "Legal warranties + arbitration in 170 NY-Convention countries"
    ],
    "inx": [
     4,
     "C",
     "Enforceable via regulated broker-dealer/ATS"
    ]
   }
  },
  {
   "cat": "compliance",
   "label": "On-chain identity",
   "exec": true,
   "cells": {
    "sost": [
     0,
     "F",
     "No on-chain identity layer today"
    ],
    "securitize": [
     4,
     "C",
     "Identity verified in regulated onboarding"
    ],
    "tokeny": [
     5,
     "C",
     "ONCHAINID is a core primitive"
    ],
    "centrifuge": [
     3,
     "",
     "Permissioned identities for participants"
    ],
    "polymesh": [
     5,
     "C",
     "Verified on-chain identity required for asset actions"
    ],
    "mattereum": [
     2,
     "",
     "Identity via legal contracts, not on-chain primitive"
    ],
    "inx": [
     4,
     "C",
     "Identity for trading eligibility"
    ]
   }
  },
  {
   "cat": "compliance",
   "label": "KYC / AML",
   "exec": true,
   "cells": {
    "sost": [
     0,
     "F",
     "No KYC/AML — future gated capability"
    ],
    "securitize": [
     5,
     "C",
     "Full regulated KYC/AML"
    ],
    "tokeny": [
     5,
     "C",
     "KYC via ONCHAINID claim issuers"
    ],
    "centrifuge": [
     4,
     "C",
     "KYC for pool participation"
    ],
    "polymesh": [
     5,
     "C",
     "KYC/AML tied to on-chain identity"
    ],
    "mattereum": [
     3,
     "C",
     "KYC as part of legal onboarding"
    ],
    "inx": [
     5,
     "C",
     "Regulated KYC/AML"
    ]
   }
  },
  {
   "cat": "compliance",
   "label": "Investor eligibility / whitelisting",
   "exec": false,
   "cells": {
    "sost": [
     0,
     "F",
     "Not implemented — future"
    ],
    "securitize": [
     5,
     "C",
     "Eligibility enforced per regulation"
    ],
    "tokeny": [
     5,
     "C",
     "Whitelisting enforced by compliance contract"
    ],
    "centrifuge": [
     4,
     "C",
     "Eligibility per pool"
    ],
    "polymesh": [
     5,
     "C",
     "Eligibility enforced in-protocol"
    ],
    "mattereum": [
     2,
     "",
     "Eligibility via legal terms"
    ],
    "inx": [
     5,
     "C",
     "Eligibility enforced for trading"
    ]
   }
  },
  {
   "cat": "compliance",
   "label": "Forced transfer / recovery",
   "exec": false,
   "cells": {
    "sost": [
     0,
     "F",
     "Not implemented — future"
    ],
    "securitize": [
     5,
     "C",
     "Recovery/forced transfer under regulated authority"
    ],
    "tokeny": [
     5,
     "C",
     "Agent role handles forced transfer, freeze, recovery"
    ],
    "centrifuge": [
     2,
     "",
     "Limited recovery outside pool permissioning"
    ],
    "polymesh": [
     5,
     "C",
     "Recovery primitives in-protocol"
    ],
    "mattereum": [
     3,
     "C",
     "Recovery via legal/arbitration process"
    ],
    "inx": [
     4,
     "C",
     "Recovery under regulated venue"
    ]
   }
  },
  {
   "cat": "compliance",
   "label": "Cap table / ownership register",
   "exec": false,
   "cells": {
    "sost": [
     2,
     "G",
     "Ownership modelled in offering layer; not a regulated register"
    ],
    "securitize": [
     5,
     "C",
     "SEC-registered transfer-agent register"
    ],
    "tokeny": [
     4,
     "C",
     "On-chain holder register via token"
    ],
    "centrifuge": [
     3,
     "",
     "Holder records per pool"
    ],
    "polymesh": [
     5,
     "C",
     "On-chain register with identity"
    ],
    "mattereum": [
     3,
     "C",
     "Ownership tied to warranted NFT"
    ],
    "inx": [
     4,
     "C",
     "Transfer-agent register (INX)"
    ]
   }
  },
  {
   "cat": "compliance",
   "label": "Regulated issuance support",
   "exec": true,
   "cells": {
    "sost": [
     0,
     "F",
     "Not a regulated issuer — public real-money execution gated OFF"
    ],
    "securitize": [
     5,
     "C",
     "SEC-registered issuance stack"
    ],
    "tokeny": [
     4,
     "C",
     "Compliance rails for regulated issuers"
    ],
    "centrifuge": [
     3,
     "",
     "Regulated fund structures"
    ],
    "polymesh": [
     4,
     "C",
     "Built for regulated assets"
    ],
    "mattereum": [
     3,
     "C",
     "Legal wrapper for regulated sales"
    ],
    "inx": [
     5,
     "C",
     "Regulated primary issuance"
    ]
   }
  },
  {
   "cat": "market",
   "label": "Primary issuance / distribution",
   "exec": true,
   "cells": {
    "sost": [
     2,
     "G",
     "Offering engines built; public execution gated"
    ],
    "securitize": [
     5,
     "C",
     "Regulated primary distribution"
    ],
    "tokeny": [
     4,
     "C",
     "Issuance rails"
    ],
    "centrifuge": [
     4,
     "C",
     "Distributes to DeFi lenders"
    ],
    "polymesh": [
     4,
     "C",
     "Primary issuance on L1"
    ],
    "mattereum": [
     3,
     "C",
     "Primary sale of rwaNFTs"
    ],
    "inx": [
     5,
     "C",
     "Regulated primary marketplace"
    ]
   }
  },
  {
   "cat": "market",
   "label": "Secondary trading",
   "exec": true,
   "cells": {
    "sost": [
     0,
     "F",
     "Asset Marketplace is future — no secondary trading"
    ],
    "securitize": [
     5,
     "C",
     "Securitize Markets ATS"
    ],
    "tokeny": [
     3,
     "",
     "Trading on venues that support ERC-3643"
    ],
    "centrifuge": [
     3,
     "",
     "Secondary via DeFi liquidity"
    ],
    "polymesh": [
     4,
     "C",
     "Settlement supports trading venues"
    ],
    "mattereum": [
     3,
     "C",
     "Secondary sale of NFTs on EVM marketplaces"
    ],
    "inx": [
     5,
     "C",
     "24/7 INX ATS secondary trading"
    ]
   }
  },
  {
   "cat": "market",
   "label": "Order book / marketplace",
   "exec": false,
   "cells": {
    "sost": [
     0,
     "F",
     "No order book — future"
    ],
    "securitize": [
     5,
     "C",
     "Regulated ATS order book"
    ],
    "tokeny": [
     1,
     "",
     "Not a marketplace operator"
    ],
    "centrifuge": [
     2,
     "",
     "DeFi markets"
    ],
    "polymesh": [
     2,
     "",
     "Venue-dependent"
    ],
    "mattereum": [
     2,
     "",
     "Third-party NFT marketplaces"
    ],
    "inx": [
     5,
     "C",
     "INX ATS order book"
    ]
   }
  },
  {
   "cat": "market",
   "label": "DeFi integrations",
   "exec": false,
   "cells": {
    "sost": [
     1,
     "F",
     "No DeFi connectivity today"
    ],
    "securitize": [
     3,
     "",
     "Selective institutional DeFi"
    ],
    "tokeny": [
     3,
     "",
     "ERC-3643 composability where permitted"
    ],
    "centrifuge": [
     5,
     "C",
     "Deep DeFi lending/borrowing — core design"
    ],
    "polymesh": [
     3,
     "",
     "DeFi via ecosystem"
    ],
    "mattereum": [
     2,
     "",
     "NFT/DeFi where compatible"
    ],
    "inx": [
     2,
     "",
     "Limited DeFi exposure; regulated-venue focus"
    ]
   }
  },
  {
   "cat": "market",
   "label": "Fiat / stablecoin settlement",
   "exec": true,
   "cells": {
    "sost": [
     2,
     "G",
     "SOST rails prepared; execution gated, no fiat rails"
    ],
    "securitize": [
     5,
     "C",
     "Atomic securities↔stablecoin settlement (FINRA-approved custody)"
    ],
    "tokeny": [
     3,
     "",
     "Settlement via host chain"
    ],
    "centrifuge": [
     4,
     "C",
     "Stablecoin settlement in DeFi"
    ],
    "polymesh": [
     5,
     "C",
     "Native on-chain settlement primitives"
    ],
    "mattereum": [
     3,
     "",
     "Settlement in crypto/fiat via partners"
    ],
    "inx": [
     4,
     "C",
     "Regulated settlement on venue"
    ]
   }
  },
  {
   "cat": "market",
   "label": "Custody integration",
   "exec": true,
   "cells": {
    "sost": [
     0,
     "F",
     "No custody — SOST never custodies the asset"
    ],
    "securitize": [
     5,
     "C",
     "FINRA-approved custody of tokenized securities"
    ],
    "tokeny": [
     3,
     "",
     "Custody via partners"
    ],
    "centrifuge": [
     3,
     "",
     "Custody via partners"
    ],
    "polymesh": [
     4,
     "C",
     "Qualified custodians in ecosystem"
    ],
    "mattereum": [
     2,
     "",
     "Physical custody via bonded warehouses/legal terms"
    ],
    "inx": [
     4,
     "C",
     "Custody via regulated partners"
    ]
   }
  },
  {
   "cat": "market",
   "label": "Established liquidity",
   "exec": false,
   "cells": {
    "sost": [
     0,
     "F",
     "No live market/liquidity"
    ],
    "securitize": [
     4,
     "C",
     "Real regulated liquidity"
    ],
    "tokeny": [
     3,
     "",
     "Liquidity where deployed"
    ],
    "centrifuge": [
     4,
     "C",
     "$1B+ private-credit originations"
    ],
    "polymesh": [
     3,
     "",
     "Growing ecosystem liquidity"
    ],
    "mattereum": [
     2,
     "",
     "Thin/curated"
    ],
    "inx": [
     4,
     "C",
     "Regulated trading liquidity"
    ]
   }
  },
  {
   "cat": "offer",
   "label": "Tokenize (divide a right)",
   "exec": true,
   "cells": {
    "sost": [
     4,
     "G",
     "Core offering — engine complete, execution gated"
    ],
    "securitize": [
     5,
     "C",
     "Core business"
    ],
    "tokeny": [
     5,
     "C",
     "Core standard"
    ],
    "centrifuge": [
     4,
     "C",
     "Pool tokenization"
    ],
    "polymesh": [
     5,
     "C",
     "Native tokenization"
    ],
    "mattereum": [
     4,
     "C",
     "rwaNFT tokenization"
    ],
    "inx": [
     4,
     "C",
     "Tokenized securities"
    ]
   }
  },
  {
   "cat": "offer",
   "label": "Auction (highest bidder)",
   "exec": true,
   "cells": {
    "sost": [
     4,
     "G",
     "Signed-bid auction engine complete; execution gated"
    ],
    "securitize": [
     -1,
     "",
     "Not part of their model"
    ],
    "tokeny": [
     -1,
     "",
     "Not part of their model"
    ],
    "centrifuge": [
     -1,
     "",
     "Not part of their model"
    ],
    "polymesh": [
     -1,
     "",
     "Not part of their model"
    ],
    "mattereum": [
     2,
     "",
     "Some assets sold via auction venues"
    ],
    "inx": [
     -1,
     "",
     "Not part of their model"
    ]
   }
  },
  {
   "cat": "offer",
   "label": "Verifiable Draw",
   "exec": true,
   "cells": {
    "sost": [
     4,
     "G",
     "Verifiable draw engine (recomputable winner) complete; execution gated"
    ],
    "securitize": [
     -1,
     "",
     "Not part of their model"
    ],
    "tokeny": [
     -1,
     "",
     "Not part of their model"
    ],
    "centrifuge": [
     -1,
     "",
     "Not part of their model"
    ],
    "polymesh": [
     -1,
     "",
     "Not part of their model"
    ],
    "mattereum": [
     -1,
     "",
     "Not part of their model"
    ],
    "inx": [
     -1,
     "",
     "Not part of their model"
    ]
   }
  },
  {
   "cat": "offer",
   "label": "Project Funding (milestones)",
   "exec": true,
   "cells": {
    "sost": [
     4,
     "G",
     "All-or-nothing, milestone-gated engine complete; execution gated"
    ],
    "securitize": [
     2,
     "",
     "Fund/entity raises, not milestone project funding"
    ],
    "tokeny": [
     -1,
     "",
     "Not part of their model"
    ],
    "centrifuge": [
     4,
     "C",
     "Finances originations/projects via pools"
    ],
    "polymesh": [
     -1,
     "",
     "Not part of their model"
    ],
    "mattereum": [
     -1,
     "",
     "Not part of their model"
    ],
    "inx": [
     3,
     "",
     "Primary raises"
    ]
   }
  },
  {
   "cat": "offer",
   "label": "Debt model",
   "exec": false,
   "cells": {
    "sost": [
     3,
     "G",
     "DEBT funding model supported; execution gated"
    ],
    "securitize": [
     4,
     "C",
     "Debt securities"
    ],
    "tokeny": [
     3,
     "",
     "Debt tokens via ERC-3643"
    ],
    "centrifuge": [
     5,
     "C",
     "Private credit is the core"
    ],
    "polymesh": [
     4,
     "C",
     "Debt instruments native"
    ],
    "mattereum": [
     -1,
     "",
     "Not part of their model"
    ],
    "inx": [
     4,
     "C",
     "Debt securities traded"
    ]
   }
  },
  {
   "cat": "offer",
   "label": "Revenue-share / royalty",
   "exec": false,
   "cells": {
    "sost": [
     3,
     "G",
     "REVENUE_SHARE + ROYALTY right types; execution gated"
    ],
    "securitize": [
     3,
     "",
     "Via structured securities"
    ],
    "tokeny": [
     2,
     "",
     "Via token terms"
    ],
    "centrifuge": [
     3,
     "",
     "Via pool economics"
    ],
    "polymesh": [
     3,
     "",
     "Via asset terms"
    ],
    "mattereum": [
     2,
     "",
     "Via legal terms"
    ],
    "inx": [
     2,
     "",
     "Via listed instruments"
    ]
   }
  },
  {
   "cat": "offer",
   "label": "Equity / SPV",
   "exec": false,
   "cells": {
    "sost": [
     3,
     "G",
     "EQUITY_SPV funding model; execution gated"
    ],
    "securitize": [
     5,
     "C",
     "Regulated equity/SPV"
    ],
    "tokeny": [
     3,
     "",
     "Equity tokens"
    ],
    "centrifuge": [
     2,
     "",
     "Fund structures"
    ],
    "polymesh": [
     4,
     "C",
     "Equity assets"
    ],
    "mattereum": [
     2,
     "",
     "Via legal wrapper"
    ],
    "inx": [
     4,
     "C",
     "Equity security tokens"
    ]
   }
  },
  {
   "cat": "tech",
   "label": "Own Layer 1",
   "exec": true,
   "cells": {
    "sost": [
     5,
     "C",
     "SOST is an independent PoW Layer 1 (ConvergenceX/SbPoW)"
    ],
    "securitize": [
     0,
     "",
     "No own L1 — issues on public chains"
    ],
    "tokeny": [
     0,
     "",
     "No own L1 — EVM standard"
    ],
    "centrifuge": [
     2,
     "",
     "Own chain history, now multichain/EVM-oriented"
    ],
    "polymesh": [
     5,
     "C",
     "Purpose-built permissioned L1"
    ],
    "mattereum": [
     0,
     "",
     "No own L1 — EVM NFTs"
    ],
    "inx": [
     0,
     "",
     "No own L1 — regulated venue"
    ]
   }
  },
  {
   "cat": "tech",
   "label": "Public verification",
   "exec": true,
   "cells": {
    "sost": [
     5,
     "C",
     "Anyone recomputes manifestHash and re-checks the anchor on a public chain"
    ],
    "securitize": [
     2,
     "",
     "Verification within regulated systems"
    ],
    "tokeny": [
     4,
     "C",
     "Public on-chain token/identity state"
    ],
    "centrifuge": [
     4,
     "C",
     "Public on-chain pool state"
    ],
    "polymesh": [
     4,
     "C",
     "Public ledger with permissioned actions"
    ],
    "mattereum": [
     3,
     "",
     "Public NFT + passport pages"
    ],
    "inx": [
     2,
     "",
     "Verification within regulated venue"
    ]
   }
  },
  {
   "cat": "tech",
   "label": "Deterministic verification",
   "exec": true,
   "cells": {
    "sost": [
     5,
     "C",
     "Canonical JSON → identical hash for everyone; MATCH/FAIL"
    ],
    "securitize": [
     1,
     "",
     "No public deterministic scheme"
    ],
    "tokeny": [
     4,
     "C",
     "Deterministic contract state"
    ],
    "centrifuge": [
     3,
     "",
     "Deterministic pool state"
    ],
    "polymesh": [
     4,
     "C",
     "Deterministic protocol state"
    ],
    "mattereum": [
     2,
     "",
     "No canonical-hash recompute scheme"
    ],
    "inx": [
     1,
     "",
     "No public deterministic scheme"
    ]
   }
  },
  {
   "cat": "tech",
   "label": "Open-source components",
   "exec": false,
   "cells": {
    "sost": [
     4,
     "C",
     "MIT-licensed core"
    ],
    "securitize": [
     2,
     "",
     "Mostly proprietary regulated stack"
    ],
    "tokeny": [
     5,
     "C",
     "ERC-3643 is an open standard"
    ],
    "centrifuge": [
     4,
     "C",
     "Open protocol"
    ],
    "polymesh": [
     4,
     "C",
     "Open-source L1"
    ],
    "mattereum": [
     2,
     "",
     "Protocol partly open"
    ],
    "inx": [
     1,
     "",
     "Proprietary venue"
    ]
   }
  },
  {
   "cat": "tech",
   "label": "Smart-contract support",
   "exec": false,
   "cells": {
    "sost": [
     2,
     "F",
     "No general smart contracts (UTXO + capsules); EVM swap contracts exist off-node"
    ],
    "securitize": [
     3,
     "",
     "Uses host-chain contracts"
    ],
    "tokeny": [
     5,
     "C",
     "ERC-3643 contracts"
    ],
    "centrifuge": [
     4,
     "C",
     "DeFi contracts"
    ],
    "polymesh": [
     4,
     "C",
     "Compliance logic in-protocol + contracts"
    ],
    "mattereum": [
     3,
     "",
     "EVM contracts for NFTs"
    ],
    "inx": [
     2,
     "",
     "Venue infra"
    ]
   }
  },
  {
   "cat": "tech",
   "label": "On-chain compliance enforcement",
   "exec": true,
   "cells": {
    "sost": [
     0,
     "F",
     "No on-chain compliance today — future"
    ],
    "securitize": [
     4,
     "C",
     "Enforced via regulated stack + tokens"
    ],
    "tokeny": [
     5,
     "C",
     "Compliance enforced in the token itself"
    ],
    "centrifuge": [
     3,
     "",
     "Permissioning"
    ],
    "polymesh": [
     5,
     "C",
     "Compliance is a protocol primitive"
    ],
    "mattereum": [
     2,
     "",
     "Compliance via legal layer"
    ],
    "inx": [
     4,
     "C",
     "Enforced at the venue"
    ]
   }
  },
  {
   "cat": "tech",
   "label": "Audit trail",
   "exec": false,
   "cells": {
    "sost": [
     5,
     "C",
     "Immutable event log + on-chain anchor"
    ],
    "securitize": [
     4,
     "C",
     "Regulated audit trail"
    ],
    "tokeny": [
     4,
     "C",
     "On-chain audit trail"
    ],
    "centrifuge": [
     4,
     "C",
     "On-chain audit trail"
    ],
    "polymesh": [
     5,
     "C",
     "On-chain audit trail with identity"
    ],
    "mattereum": [
     3,
     "",
     "Passport history"
    ],
    "inx": [
     4,
     "C",
     "Regulated trade audit trail"
    ]
   }
  }
 ],
 "categories": [
  [
   "overview",
   "Overview"
  ],
  [
   "asset",
   "Asset & Evidence"
  ],
  [
   "token",
   "Tokenization"
  ],
  [
   "compliance",
   "Compliance"
  ],
  [
   "market",
   "Market"
  ],
  [
   "offer",
   "Offerings"
  ],
  [
   "tech",
   "Technology"
  ]
 ]
};
