import { chromium } from 'playwright';
import { writeFileSync } from 'fs';

const FONTS = '/tmp/claude-0/-home-user-NeuroForge/aee9739c-b05c-557b-b2d9-663b03ab89bb/scratchpad/fonts';

/* the notice — the office's wanted poster. 12 x 16 in at 300 dpi
   (1800 x 2400 css px at deviceScaleFactor 2). bone ink for dark
   garments; the cardinal on the frame is the only red. */
const html = `<!doctype html><html><head><style>
@font-face { font-family:'IM Fell English SC'; font-weight:400; src:url('${FONTS}/f5.woff2') format('woff2'); }
@font-face { font-family:'Courier Prime'; font-weight:400; src:url('${FONTS}/f2.woff2') format('woff2'); }
@font-face { font-family:'Courier Prime'; font-weight:700; src:url('${FONTS}/f4.woff2') format('woff2'); }
* { margin:0; box-sizing:border-box; }
body { background:transparent; }
.wrap {
  width:1800px; height:2400px;
  padding:56px;
  color:#E6E0D3;
  text-align:center;
}
.sheet {
  height:100%;
  border:5px solid #E6E0D3;
  outline:2px solid #E6E0D3;
  outline-offset:14px;
  padding:90px 110px 70px;
  display:flex; flex-direction:column; align-items:center;
}
.office {
  font-family:'Courier Prime',monospace; font-size:30px;
  letter-spacing:0.34em; text-transform:uppercase;
}
.rule { width:420px; height:2px; background:#E6E0D3; opacity:0.65; margin:34px 0; }
h1 {
  font-family:'IM Fell English SC',serif; font-weight:400;
  font-size:215px; line-height:1; letter-spacing:0.06em;
}
.sub {
  font-family:'Courier Prime',monospace; font-size:33px;
  letter-spacing:0.22em; text-transform:uppercase; margin-top:26px;
}
.framebox { position:relative; margin:120px 0 34px; }
.frame {
  width:1020px; height:660px;
  border:4px solid #E6E0D3;
  outline:2px solid #E6E0D3; outline-offset:12px;
  display:grid; place-items:center;
  padding:60px;
}
.frame p {
  font-family:'Courier Prime',monospace; font-size:37px;
  line-height:2; letter-spacing:0.06em;
}
.bird { position:absolute; top:-112px; right:80px; width:142px; height:112px; }
.classline {
  font-family:'Courier Prime',monospace; font-size:31px;
  letter-spacing:0.2em; text-transform:uppercase; margin-bottom:44px;
}
.body {
  font-family:'Courier Prime',monospace; font-size:36px;
  line-height:2; max-width:1210px;
}
.reward {
  font-family:'IM Fell English SC',serif; font-weight:400;
  font-size:96px; line-height:1.1; letter-spacing:0.05em; margin-top:56px; white-space:nowrap;
}
.reward-sub {
  font-family:'Courier Prime',monospace; font-size:33px;
  letter-spacing:0.14em; margin-top:20px;
}
.foot { margin-top:auto; padding-top:44px; }
.foot svg { width:132px; height:132px; opacity:0.95; }
.closing {
  font-family:'Courier Prime',monospace; font-size:33px;
  letter-spacing:0.18em; margin-top:26px;
}
</style></head><body><div class="wrap"><div class="sheet">

  <p class="office">federal photography project</p>
  <p class="office" style="margin-top:14px">field office e &middot; southern region &middot; est. MCMXXXV</p>

  <div class="rule"></div>

  <h1>NOTICE</h1>
  <p class="sub">concerning the animal of this county</p>

  <div class="framebox">
    <svg class="bird" viewBox="0 0 140 110" xmlns="http://www.w3.org/2000/svg">
      <path fill="#7A1D1D" d="M20 98 L46 72 C42 58 50 44 64 40 C66 30 72 24 78 20 L82 8 L88 20 C96 24 100 32 100 40 L112 46 L100 52 C100 66 92 76 78 80 C70 83 60 84 52 82 L30 102 Z"/>
      <path d="M68 82 L68 92" stroke="#7A1D1D" stroke-width="2" opacity="0.8"/>
    </svg>
    <div class="frame">
      <p>the office has no photograph<br>of this animal.<br><br>what it does is in the file.<br>what it is, is not.</p>
    </div>
  </div>

  <p class="classline">exhibit: plate i &middot; class .0100 &middot; filed: damage only</p>

  <p class="body">fences at the east quarter found opened from the inside.
  branches on the creek road broken at nine feet; nothing in the
  county stands nine feet. the flood mark moved up a dry wall.
  no prints were taken because no prints were found.</p>

  <p class="reward">NO REWARD IS OFFERED</p>
  <p class="reward-sub">the office does not hunt. it keeps the record.</p>

  <div class="foot">
    <svg viewBox="0 0 240 240" xmlns="http://www.w3.org/2000/svg">
      <g fill="none" stroke="#E6E0D3">
        <circle cx="120" cy="120" r="116" stroke-width="3"/>
        <circle cx="120" cy="120" r="104" stroke-width="1.25"/>
      </g>
      <g stroke="#E6E0D3" fill="none" stroke-linecap="round">
        <path stroke-width="4" d="M120 172 L120 112"/>
        <path stroke-width="2.5" d="M120 138 L99 115 M99 115 L86 104 M99 115 L104 96 M120 128 L141 106 M141 106 L154 98 M141 106 L137 90 M120 112 L120 94 M120 94 L112 82 M120 94 L128 83"/>
        <path stroke-width="2" d="M98 172 L142 172 M108 178 L132 178"/>
      </g>
    </svg>
    <p class="closing">the file is not closed.</p>
  </div>

</div></div></body></html>`;

const browser = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium-1194/chrome-linux/chrome' });
const page = await browser.newPage({ viewport: { width: 1900, height: 2500 }, deviceScaleFactor: 2 });
writeFileSync('job-notice.html', html);
await page.goto('file://' + process.cwd() + '/job-notice.html');
await page.waitForTimeout(500);
const el = await page.$('.wrap');
await el.screenshot({ path: 'out/bandersnatch-notice-bone.png', omitBackground: true });
await browser.close();
console.log('rendered the notice');
