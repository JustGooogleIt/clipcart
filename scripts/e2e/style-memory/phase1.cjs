const L = require('./lib.cjs');
(async () => {
  const { b, ctx, p } = await L.open(false);
  await p.goto(L.BASE + '/', { waitUntil: 'networkidle' });
  await p.getByRole('button', { name: 'Try the sample scene' }).click();
  await p.getByRole('button', { name: /Draw a box around a garment/ }).click();
  await p.mouse.move(200, 420); await p.mouse.down(); await p.mouse.move(350, 660, { steps: 12 }); await p.mouse.up();
  await p.locator('#manual-desc').fill('denim jacket');
  await p.getByRole('button', { name: 'Use this garment' }).click();
  await p.waitForTimeout(800);
  let c = await L.search(p);
  L.step('baseline search returns results with no personalization', c.length >= 2 && c.every(x => !x.personalization), c);
  const moto = c.find(x => /Calvin Klein/.test(x.title));
  L.step('brown Calvin Klein moto jacket is among results', !!moto);
  // 1. Save an item
  const motoCard = p.locator('.card-title', { hasText: 'Calvin Klein' }).locator('xpath=ancestor::*[.//button[contains(@class,"btn-save")]][1]');
  await motoCard.locator('.btn-save').click();
  await p.waitForTimeout(1200);
  c = await L.cards(p);
  L.step('Save toggles to Saved', /Saved/.test(c.find(x => /Calvin Klein/.test(x.title)).save), c.map(x => [x.title.slice(0, 30), x.save]));
  await p.screenshot({ path: L.S + '/shots/p1-01-saved.png', fullPage: true });
  // 2. Accept a preference from a style note
  await L.openPanel(p);
  L.step('panel lists the saved item', /Saved items.*Calvin Klein/.test(await L.panelText(p)));
  L.step('panel names the rule-based reader honestly', /Read by: Rule-based parser/.test(await L.panelText(p)), (await L.panelText(p)).match(/Read by:[^.]*\./)?.[0]);
  await p.locator('#style-note').fill('I love brown, I hate orange');
  await p.getByRole('button', { name: 'Read it' }).click();
  await p.locator('.mem-proposals').waitFor();
  const props = (await p.locator('.mem-proposals').innerText()).replace(/\s+/g, ' ');
  L.step('rule parser proposes brown like with a clean quote', /love brown”/.test(props) && !/love brown, I/.test(props), props);
  const mem0 = await L.api(p, '/api/style/memories?status=all');
  L.step('proposals are not saved before acceptance', mem0.memories.length === 0, mem0.memories.length);
  // accept only the brown like: untick orange
  const orange = p.locator('.mem-proposal', { hasText: /orange/i }).locator('input[type=checkbox]');
  if (await orange.count()) await orange.uncheck();
  await p.getByRole('button', { name: 'Save selected' }).click();
  await p.waitForTimeout(1200);
  const mem1 = (await L.api(p, '/api/style/memories')).memories;
  L.step('accepted preference saved as a stated style-note memory', mem1.length === 1 && mem1[0].kind === 'color_like' && mem1[0].value === 'brown' && mem1[0].origin === 'stated' && mem1[0].source === 'style_note', mem1.map(m => [m.kind, m.value, m.origin, m.source]));
  await p.screenshot({ path: L.S + '/shots/p1-02-panel.png' });
  await L.closePanel(p);
  // 3. Search again: supported personalization reason
  c = await L.search(p);
  const m2 = c.find(x => /Calvin Klein/.test(x.title));
  L.step('re-search shows the brown reason on the brown jacket', m2 && /You said you like brown/.test(m2.personalization || ''), c.map(x => [x.title.slice(0, 30), x.personalization]));
  L.step('reason only on the matching item', c.filter(x => x.personalization).length === 1);
  L.step('saved state survives re-search', /Saved/.test(m2.save));
  await p.locator('.card-personal').first().scrollIntoViewIfNeeded();
  await p.screenshot({ path: L.S + '/shots/p1-03-reason.png' });
  await ctx.storageState({ path: L.STATE });
  const ev = (await L.api(p, '/api/style/events')).events;
  require('fs').writeFileSync(L.S + '/phase1-state.json', JSON.stringify({ memories: mem1, events: ev, cards: c }, null, 2));
  await b.close();
  process.exit(L.save('phase1') ? 0 : 1);
})();
