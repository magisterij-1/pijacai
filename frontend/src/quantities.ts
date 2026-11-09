// — natančna decimalna pretvorba in oblikovanje količin.
// Količine in vsote ohranimo kot cela števila tisočink.
export function milli(value: string): bigint {
  const [whole, fraction = ""] = value.split(".");
  return BigInt(whole) * 1000n + BigInt(fraction.padEnd(3, "0"));
}

export function formatQuantity(value: bigint): string {
  return `${(value / 1000n).toLocaleString("sl-SI")},${(value % 1000n).toString().padStart(3, "0")}`;
}

// Predogled recepture lahko vsebuje več kot 3 decimalna mesta ali zapis z eksponentom.
// Decimalni niz razširimo brez pretvorbe celotne količine v Number.
export function formatDecimal(value: string): string {
  const match = /^([+-]?)(\d+)(?:\.(\d*))?(?:[eE]([+-]?\d+))?$/.exec(value);
  if (!match) return value;
  const [, sign, integer, fraction = "", exponent = "0"] = match;
  const shift = Number(exponent);
  if (!Number.isSafeInteger(shift) || Math.abs(shift) > 1000) return value;
  const digits = integer + fraction;
  const position = integer.length + shift;
  let whole: string;
  let decimal: string;
  if (position <= 0) {
    whole = "0"; decimal = "0".repeat(-position) + digits;
  } else if (position >= digits.length) {
    whole = digits + "0".repeat(position - digits.length); decimal = "";
  } else {
    whole = digits.slice(0, position); decimal = digits.slice(position);
  }
  decimal = decimal.replace(/0+$/, "");
  return `${sign === "-" ? "-" : ""}${BigInt(whole).toLocaleString("sl-SI")}${decimal ? `,${decimal}` : ""}`;
}
