import { chromium } from 'playwright';
import { writeFileSync, mkdirSync } from 'fs';

mkdirSync('out', { recursive: true });

const FONTS = '/tmp/claude-0/-home-user-NeuroForge/aee9739c-b05c-557b-b2d9-663b03ab89bb/scratchpad/fonts';

/* ---- the seal, print edition — arc text set in IM Fell English SC ---- */
const seal = (color) => `<!doctype html><html><head><style>
@font-face { font-family:'IM Fell English SC'; font-weight:400; src:url('${FONTS}/f5.woff2') format('woff2'); }
* { margin:0; } body { background: transparent; }
.wrap { display:inline-block; }
svg { display:block; width: 1500px; height: 1500px; }
</style></head><body><div class="wrap">
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 240 240">
  <defs>
    <path id="arc-top" d="M 30 120 A 90 90 0 0 1 210 120"/>
    <path id="arc-bottom" d="M 32 120 A 88 88 0 0 0 208 120"/>
  </defs>
  <g fill="none" stroke="${color}">
    <circle cx="120" cy="120" r="116" stroke-width="2"/>
    <circle cx="120" cy="120" r="111" stroke-width="0.75"/>
    <circle cx="120" cy="120" r="72" stroke-width="0.75"/>
  </g>
  <g font-family="'IM Fell English SC', serif" fill="${color}">
    <text font-size="12" letter-spacing="1.6">
      <textPath href="#arc-top" startOffset="50%" text-anchor="middle">PARVA PUELLA · MAGNA SOMNIA</textPath>
    </text>
    <text font-size="10" letter-spacing="1.5">
      <textPath href="#arc-bottom" startOffset="50%" text-anchor="middle">BY HER HAND · MCMXXXV —</textPath>
    </text>
  </g>
  <g stroke="${color}" fill="none" stroke-linecap="round">
    <path stroke-width="2.25" d="M120 160 L120 118"/>
    <path stroke-width="1.5" d="M120 134 L103 115 M103 115 L93 106 M103 115 L107 100 M93 106 L86 101 M93 106 L91 96 M107 100 L102 92 M107 100 L113 91"/>
    <path stroke-width="1.5" d="M120 127 L137 109 M137 109 L147 101 M137 109 L134 96 M147 101 L154 97 M147 101 L147 91 M134 96 L129 88 M134 96 L139 87"/>
    <path stroke-width="1.5" d="M120 118 L120 103 M120 103 L114 93 M120 103 L126 94"/>
    <path stroke-width="1.25" d="M102 160 L138 160 M110 164 L130 164"/>
  </g>
</svg></div></body></html>`;

/* ---- the cardinal, plate ii — the only red in the file ---- */
const cardinal = `<!doctype html><html><head><style>
* { margin:0; } body { background: transparent; }
.wrap { display:inline-block; }
svg { display:block; width: 2800px; height: 2200px; }
</style></head><body><div class="wrap">
<svg viewBox="0 0 140 110" xmlns="http://www.w3.org/2000/svg">
  <path fill="#7A1D1D" d="M20 98 L46 72 C42 58 50 44 64 40 C66 30 72 24 78 20 L82 8 L88 20 C96 24 100 32 100 40 L112 46 L100 52 C100 66 92 76 78 80 C70 83 60 84 52 82 L30 102 Z"/>
  <path d="M68 82 L68 92" stroke="#7A1D1D" stroke-width="2" opacity="0.8"/>
  <path d="M12 92 L128 92" stroke="#7A1D1D" stroke-width="1.5" opacity="0.5"/>
</svg></div></body></html>`;

/* ---- back-neck tagline, courier prime ---- */
const tagline = (color) => `<!doctype html><html><head><style>
@font-face { font-family:'Courier Prime'; font-weight:400; src:url('${FONTS}/f2.woff2') format('woff2'); }
* { margin:0; } body { background: transparent; }
.wrap { display:inline-block; padding: 40px 60px; }
p { font-family:'Courier Prime', monospace; font-weight:400; font-size:110px;
    letter-spacing:0.08em; color:${color}; white-space:nowrap; }
</style></head><body><div class="wrap"><p>the file is not closed.</p></div></body></html>`;

/* ---- wordmark, print edition (same spec as site renders) ---- */
const wordmark = (color) => `<!doctype html><html><head><style>
@font-face { font-family:'IM Fell English SC'; font-weight:400; src:url('${FONTS}/f5.woff2') format('woff2'); }
* { margin:0; } body { background: transparent; }
.wrap { display:inline-block; padding: 60px 90px; }
h1 { font-family:'IM Fell English SC', serif; font-weight:400; font-size:260px;
     line-height:1.02; letter-spacing:0.045em; color:${color}; white-space:nowrap; }
</style></head><body><div class="wrap"><h1>bandersnatch</h1></div></body></html>`;

const JOBS = [
  ['seal-bone', seal('#E6E0D3'), { width: 1700, height: 1700 }],
  ['seal-ink', seal('#100E0C'), { width: 1700, height: 1700 }],
  ['seal-silver', seal('#8E897F'), { width: 1700, height: 1700 }],
  ['cardinal-red', cardinal, { width: 3000, height: 2400 }],
  ['tagline-bone', tagline('#E6E0D3'), { width: 2400, height: 400 }],
  ['tagline-ink', tagline('#100E0C'), { width: 2400, height: 400 }],
  ['wordmark-bone', wordmark('#E6E0D3'), { width: 3400, height: 700 }],
  ['wordmark-ink', wordmark('#100E0C'), { width: 3400, height: 700 }],
];

const browser = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium-1194/chrome-linux/chrome' });
for (const [name, html, viewport] of JOBS) {
  const page = await browser.newPage({ viewport, deviceScaleFactor: 2 });
  const f = `job-${name}.html`;
  writeFileSync(f, html);
  await page.goto('file://' + process.cwd() + '/' + f);
  await page.waitForTimeout(400);
  const el = await page.$('.wrap');
  await el.screenshot({ path: `out/bandersnatch-${name}.png`, omitBackground: true });
  await page.close();
  console.log('rendered', name);
}
await browser.close();
