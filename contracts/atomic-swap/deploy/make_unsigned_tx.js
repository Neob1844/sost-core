// make_unsigned_tx.js — emit an UNSIGNED contract-creation tx for AtomicSwapHTLCv2.
// The owner signs it LOCALLY in their own wallet (hardware wallet, MetaMask via a
// local signer, or `cast`); no private key ever touches this repo, the relay, or chat.
//   node make_unsigned_tx.js <chainId> [nonce] [maxFeeGwei] [maxPriorityGwei] > unsigned-tx.json
const fs = require('fs');
const bytecode = fs.readFileSync(__dirname + '/AtomicSwapHTLCv2.bytecode.txt', 'utf8').trim();
const chainId = parseInt(process.argv[2] || '11155111', 10);   // default Sepolia
const nonce = process.argv[3] !== undefined ? parseInt(process.argv[3], 10) : null; // owner fills from their account
const maxFeeGwei = parseFloat(process.argv[4] || '25');
const maxPriorityGwei = parseFloat(process.argv[5] || '1.5');
const GAS = 1400000; // >= creation gas 1,234,479 with headroom
const tx = {
  type: '0x2',                       // EIP-1559
  chainId: '0x' + chainId.toString(16),
  to: null,                          // contract creation
  value: '0x0',
  data: bytecode,
  gas: '0x' + GAS.toString(16),
  maxFeePerGas: '0x' + Math.round(maxFeeGwei * 1e9).toString(16),
  maxPriorityFeePerGas: '0x' + Math.round(maxPriorityGwei * 1e9).toString(16),
  nonce: nonce === null ? null : '0x' + nonce.toString(16),
  _note: 'UNSIGNED. Fill nonce from your deployer account, review gas/fees, sign LOCALLY in your wallet. Never share the private key.',
  _est_gas: GAS, _est_cost_eth_at_maxfee: (GAS * maxFeeGwei) / 1e9
};
process.stdout.write(JSON.stringify(tx, null, 2) + '\n');
