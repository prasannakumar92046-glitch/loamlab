/* LoamLab front-end motion + small interactive widgets (no dependencies). */
(() => {
  const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];

  /* 1 ── header turns glassy once you scroll */
  const top = document.querySelector('.top');
  const onScroll = () => top && top.classList.toggle('scrolled', scrollY > 24);
  addEventListener('scroll', onScroll, { passive: true }); onScroll();

  /* 2 ── headline "ghost trail": duplicate the heading so a faint copy settles into it */
  $$('.gt').forEach(el => {
    const html = el.innerHTML;
    el.innerHTML = `<span class="real">${html}</span><span class="ghost" aria-hidden="true">${html}</span>`;
  });

  /* 3 ── stagger index for children of .stagger */
  $$('.stagger').forEach(p => [...p.children].forEach((c, i) => { c.classList.add('rv'); c.style.setProperty('--i', i); }));
  $$('.rv:not(.stagger > *)').forEach(el => { if (!el.style.getPropertyValue('--i')) el.style.setProperty('--i', el.dataset.i || 0); });

  /* 4 ── reveal on enter */
  const reveal = el => {
    el.classList.add('in');
    $$('.bar i[data-w]', el).forEach(b => b.style.width = b.dataset.w + '%');
    $$('.phbar .mark[data-left]', el).forEach(m => m.style.left = m.dataset.left + '%');
    $$('.track .fill[data-w]', el).forEach(f => f.style.width = f.dataset.w + '%');
    $$('.ring[data-p]', el).forEach(r => r.style.setProperty('--p', r.dataset.p));
  };
  const targets = $$('.gt,.rv,.imgcard,.wordmark,.steps,.reveal-group,.acard,.metric,.hz.slide');
  if (!('IntersectionObserver' in window) || reduce) targets.forEach(reveal);
  else {
    const io = new IntersectionObserver(es => es.forEach(e => { if (e.isIntersecting) { reveal(e.target); io.unobserve(e.target); } }), { threshold: .14, rootMargin: '0px 0px -6% 0px' });
    targets.forEach(t => io.observe(t));
  }

  /* 5 ── outgoing section dims/blurs while the next section arrives */
  const secs = $$('.sec');
  if (secs.length && !reduce) {
    let tick = false;
    const update = () => {
      tick = false;
      const vh = innerHeight;
      secs.forEach(s => {
        const r = s.getBoundingClientRect();
        // how far the section's bottom has risen into the top 45% of the viewport
        const out = Math.min(1, Math.max(0, (vh * .45 - r.bottom) / (vh * .45)) * -1 + 1);
        const leaving = r.bottom < vh * .45 ? Math.min(1, (vh * .45 - r.bottom) / (vh * .45)) : 0;
        s.style.setProperty('--out', leaving.toFixed(3));
      });
    };
    addEventListener('scroll', () => { if (!tick) { tick = true; requestAnimationFrame(update); } }, { passive: true });
    update();
  }

  /* 6 ── nav: smooth anchor scroll + active section highlight */
  const links = $$('.nav a[href*="#"]');
  const sections = links.map(a => document.getElementById(a.hash.slice(1))).filter(Boolean);
  if (sections.length && 'IntersectionObserver' in window) {
    const so = new IntersectionObserver(es => es.forEach(e => {
      if (e.isIntersecting) links.forEach(a => a.classList.toggle('active', a.hash === '#' + e.target.id));
    }), { threshold: .45 });
    sections.forEach(s => so.observe(s));
  }

  /* 7 ── page-to-page fade */
  document.addEventListener('click', e => {
    const a = e.target.closest('a[href]');
    if (!a || a.target || e.metaKey || e.ctrlKey || e.shiftKey || a.hasAttribute('download')) return;
    const u = new URL(a.href, location.href);
    if (u.origin !== location.origin || (u.pathname === location.pathname && u.hash) || u.pathname.endsWith('.pdf')) return;
    if (reduce) return;
    e.preventDefault(); document.body.classList.add('leaving');
    setTimeout(() => location.href = a.href, 260);
  });
  addEventListener('pageshow', e => { if (e.persisted) document.body.classList.remove('leaving'); });

  /* 8 ── interactive soil horizons (home) */
  const HZ = {
    o: ['O-Horizon: Organic Humus', '0–5 cm', 'Surface litter and decomposing organic matter. Rich in biological activity; a major store of carbon and slow-release nutrients.'],
    a: ['A-Horizon: Mineral Topsoil', '5–25 cm', 'Mixed mineral and humus layer where most roots and microbes live. Typical lab focus for available N, P, K, pH and organic carbon.'],
    b: ['B-Horizon: Subsoil', '25–60 cm', 'Zone where clay, iron oxides and leached minerals accumulate. Influences drainage, rooting depth and deep nutrient reserves.'],
    c: ['C-Horizon: Substratum', '60+ cm', 'Weathered parent material that is little affected by soil-forming processes. Sets the long-term mineral character of the profile.']
  };
  const detail = document.getElementById('hz-detail');
  $$('#strata-list .hz').forEach(row => row.addEventListener('click', () => {
    $$('#strata-list .hz').forEach(r => r.classList.remove('sel')); row.classList.add('sel');
    const d = HZ[row.dataset.h]; if (!d || !detail) return;
    detail.classList.add('swap');
    setTimeout(() => {
      detail.querySelector('h3').textContent = d[0];
      detail.querySelector('.depth').textContent = d[1];
      detail.querySelector('p').textContent = d[2];
      detail.classList.remove('swap');
    }, 260);
  }));

  /* 9 ── quick assessment (home). Indicative booking guidance only — not a diagnosis. */
  const qa = document.getElementById('qa');
  if (qa) {
    const out = document.getElementById('reco');
    const panelInfo = {
      'Standard Fertility Panel': ['pH · EC · OC · N · P · K', 'Covers soil reaction, salinity, organic carbon and the three major nutrients — the usual starting point for routine crop planning.'],
      'Micronutrient Screen': ['Zn · Fe · Cu · Mn · B', 'Targets trace elements. Useful when major nutrients are adequate but crops still show patchy growth or leaf symptoms.'],
      'Complete Soil Health': ['Full 11-parameter panel', 'Combines fertility and micronutrients for a whole-soil picture — best for poor yields, new land or persistent problems.']
    };
    const pick = () => {
      const crop = qa.crop.value, yld = qa.yield.value, wet = qa.moisture.value;
      let p = 'Standard Fertility Panel', why = `For ${crop.toLowerCase()} on reasonable ground, the Standard Fertility Panel is the usual starting point.`;
      if (yld === 'Poor') { p = 'Complete Soil Health'; why = `Poor yields in ${crop.toLowerCase()} can have several causes, so a full panel avoids testing blind.`; }
      else if (yld === 'Good' && ['Vegetables', 'Orchard / Plantation'].includes(crop)) { p = 'Micronutrient Screen'; why = `Yields are good, so major nutrients are probably being managed — a micronutrient screen checks the finer details for ${crop.toLowerCase()}.`; }
      else if (wet === 'Waterlogged') { p = 'Standard Fertility Panel'; why = 'Waterlogged soils often show salinity and pH shifts; the Standard panel includes EC and pH.'; }
      return [p, why];
    };
    const render = () => {
      const [p, why] = pick();
      out.classList.add('swap');
      setTimeout(() => {
        out.querySelector('h3').textContent = p;
        out.querySelector('.params').textContent = panelInfo[p][0];
        out.querySelector('p').textContent = why + ' ' + panelInfo[p][1];
        out.querySelector('a').href = '/book?panel=' + encodeURIComponent(p);
        out.classList.remove('swap');
      }, 240);
    };
    qa.addEventListener('change', render);
  }

  /* 10 ── demo sign-in helper */
  $$('[data-fill-email]').forEach(b => b.addEventListener('click', () => {
    const f = b.closest('form') || document.querySelector('form');
    f.email.value = b.dataset.fillEmail; f.password.value = b.dataset.fillPass;
    const r = f.querySelector('input[name=role][value="' + b.dataset.fillRole + '"]'); if (r) r.checked = true;
    f.password.focus();
  }));
})();
