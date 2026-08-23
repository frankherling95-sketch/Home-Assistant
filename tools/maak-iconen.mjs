// Genereert de app-iconen als PNG, zonder externe pakketten.
// Het merk is een trap: drie oplopende balken — de werkvolgorde waar
// de hele app om draait.
//
//   node tools/maak-iconen.mjs
//
import { deflateSync } from "node:zlib";
import { writeFileSync, mkdirSync } from "node:fs";
import { fileURLToPath } from "node:url";

const WORTEL = fileURLToPath(new URL("../", import.meta.url));

const crcTabel = (() => {
  const t = new Uint32Array(256);
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    t[n] = c >>> 0;
  }
  return t;
})();

function crc32(buf) {
  let c = 0xffffffff;
  for (const b of buf) c = crcTabel[(c ^ b) & 0xff] ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}

function chunk(type, data) {
  const len = Buffer.alloc(4);
  len.writeUInt32BE(data.length);
  const body = Buffer.concat([Buffer.from(type, "ascii"), data]);
  const crc = Buffer.alloc(4);
  crc.writeUInt32BE(crc32(body));
  return Buffer.concat([len, body, crc]);
}

function png(width, height, rgba) {
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(width, 0);
  ihdr.writeUInt32BE(height, 4);
  ihdr[8] = 8;   // bitdiepte
  ihdr[9] = 6;   // RGBA
  const rijen = Buffer.alloc((width * 4 + 1) * height);
  for (let y = 0; y < height; y++) {
    rijen[y * (width * 4 + 1)] = 0; // filtertype: geen
    rgba.copy(rijen, y * (width * 4 + 1) + 1, y * width * 4, (y + 1) * width * 4);
  }
  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    chunk("IHDR", ihdr),
    chunk("IDAT", deflateSync(rijen, { level: 9 })),
    chunk("IEND", Buffer.alloc(0)),
  ]);
}

function tekenIcoon(maat) {
  const buf = Buffer.alloc(maat * maat * 4);
  const grond = [0x1b, 0x49, 0xc4];        // blauwdrukblauw
  const wit = [0xff, 0xff, 0xff];
  const straal = maat * 0.22;              // afgeronde hoeken

  // Drie treden die naar rechts omhoog lopen, met de stootborden ertussen.
  const d = maat * 0.085;          // dikte van een tree
  const tred = maat * 0.235;       // lengte van een tree
  const stap = maat * 0.175;       // hoogteverschil per tree
  const x0 = maat * 0.16;
  const y0 = maat * 0.66;          // onderste tree

  const vlakken = [];
  for (let i = 0; i < 3; i++) {
    const x = x0 + i * (tred - d);
    const y = y0 - i * stap;
    vlakken.push([x, y, tred, d]);                       // tree
    if (i > 0) vlakken.push([x, y, d, stap + d]);        // stootbord
  }

  for (let y = 0; y < maat; y++) {
    for (let x = 0; x < maat; x++) {
      const i = (y * maat + x) * 4;
      // buiten de afgeronde hoek: doorzichtig
      const dx = Math.min(x, maat - 1 - x), dy = Math.min(y, maat - 1 - y);
      let binnen = true;
      if (dx < straal && dy < straal) {
        const a = straal - dx, b = straal - dy;
        binnen = a * a + b * b <= straal * straal;
      }
      if (!binnen) { buf[i + 3] = 0; continue; }

      let kleur = grond;
      for (const [vx, vy, vb, vh] of vlakken) {
        if (x >= vx && x < vx + vb && y >= vy && y < vy + vh) { kleur = wit; break; }
      }
      buf[i] = kleur[0]; buf[i + 1] = kleur[1]; buf[i + 2] = kleur[2]; buf[i + 3] = 255;
    }
  }
  return png(maat, maat, buf);
}

mkdirSync(WORTEL + "icons", { recursive: true });
for (const maat of [180, 192, 512]) {
  const bestand = `icons/icoon-${maat}.png`;
  writeFileSync(WORTEL + bestand, tekenIcoon(maat));
  console.log(`${bestand} geschreven`);
}
