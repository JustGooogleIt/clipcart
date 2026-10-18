/**
 * Injected by esbuild so @solana/web3.js gets Node's Buffer from the real
 * `buffer` package (browser build), not a hand-rolled fake.
 */
import { Buffer } from "buffer";

export { Buffer };
