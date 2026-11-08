// Količine in vsote ohranimo kot cela števila tisočink.
export function milli(value: string): bigint {
  const [whole, fraction = ""] = value.split(".");
  return BigInt(whole) * 1000n + BigInt(fraction.padEnd(3, "0"));
}

export function formatQuantity(value: bigint): string {
  return `${(value / 1000n).toLocaleString("sl-SI")},${(value % 1000n).toString().padStart(3, "0")}`;
}
