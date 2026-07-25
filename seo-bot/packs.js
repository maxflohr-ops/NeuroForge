// packs.js — turns the live catalog into ready-to-paste listing packs for
// marketplaces that have no posting API (poshmark, depop, grailed) and
// draft copy for ones that do (ebay, etsy). the office writes the words;
// a human pastes them. no marketplace terms are violated by a clipboard.

const SITE = 'https://bandersnatch.world';

const HASHTAGS = [
  '#southerngothic', '#gothic', '#screenprint', '#limitededition',
  '#darkacademia', '#ethelcain', '#vintagestyle', '#graphictee',
  '#altfashion', '#americana',
];

function firstSentence(text) {
  const m = (text || '').split(/(?<=\.)\s+/)[0] || '';
  return m.length > 160 ? m.slice(0, 157) + '…' : m;
}

function lotNumber(title) {
  const m = title.match(/lot no\.\s*(\d+)/i);
  return m ? m[1] : '—';
}

function buildPacks(catalog) {
  return catalog.map((p) => {
    const lot = lotNumber(p.title);
    const epigraph = firstSentence(p.description);
    const shared = {
      lot,
      title: p.title,
      price: p.price,
      sizes: p.sizes,
      photos: p.images,
      storeUrl: p.url,
      loreUrl: `${SITE}/file.html`,
    };
    const longDesc =
      `${p.description}\n\n` +
      `from BANDERSNATCH — a southern gothic world that sells clothing. ` +
      `each holding is screen printed in an edition of 24, numbered by hand, sealed in wax. ` +
      `the office does not restock.\n\n` +
      `the full file: ${SITE}`;

    return {
      ...shared,
      poshmark: {
        title: `BANDERSNATCH ${p.title.replace(/lot no\.\s*\d+\s*·\s*/i, '')} — ltd edition of 24 screen print`.slice(0, 80),
        description: longDesc,
        category: 'Men > Shirts > Tees - Short Sleeve',
        brand: 'Independent / Boutique',
        notes: 'new with tags · smoke-free · numbered edition — state the number when it ships',
      },
      depop: {
        description: `${epigraph}\n\n${p.title} · edition of 24, numbered by hand · screen printed\n\nsizes ${p.sizes.join('/')}\n\n${HASHTAGS.slice(0, 5).join(' ')}`,
        hashtags: HASHTAGS,
      },
      grailed: {
        designer: 'BANDERSNATCH',
        title: p.title,
        description: longDesc,
        tags: ['southern gothic', 'screen print', 'limited edition', 'americana'],
      },
      ebay: {
        title: `BANDERSNATCH ${p.title} Limited Edition 24 Screen Print Tee Southern Gothic`.slice(0, 80),
        description: longDesc,
        condition: 'New with tags',
      },
      etsy: {
        title: `${p.title} — southern gothic screen print tee, edition of 24`.slice(0, 140),
        description: longDesc,
        tags: ['southern gothic', 'screen print tee', 'limited edition', 'dark academia', 'gothic clothing', 'americana', 'graphic tee'].slice(0, 13),
      },
    };
  });
}

function packsMarkdown(packs) {
  const lines = ['# bandersnatch — listing packs', '', '_generated from the live catalog. copy, paste, list. the office wrote the words._', ''];
  for (const p of packs) {
    lines.push(`---`, ``, `## lot ${p.lot} · ${p.title} · $${p.price}`, ``);
    lines.push(`**store:** ${p.storeUrl}`);
    lines.push(`**sizes:** ${p.sizes.join(', ')}`);
    lines.push(`**photos:** ${p.photos.map((u, i) => `[${i + 1}](${u})`).join(' ')}`, ``);
    lines.push(`### poshmark`, `**title:** ${p.poshmark.title}`, `**category:** ${p.poshmark.category}`, `**notes:** ${p.poshmark.notes}`, '', '```', p.poshmark.description, '```', '');
    lines.push(`### depop`, '```', p.depop.description, '```', '');
    lines.push(`### grailed`, `**designer:** ${p.grailed.designer}`, '```', p.grailed.description, '```', '');
    lines.push(`### ebay`, `**title:** ${p.ebay.title}`, '');
    lines.push(`### etsy`, `**title:** ${p.etsy.title}`, `**tags:** ${p.etsy.tags.join(', ')}`, '');
  }
  return lines.join('\n');
}

module.exports = { buildPacks, packsMarkdown };
