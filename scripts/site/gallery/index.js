
    (function () {
      var de = document.documentElement;
      var grid = document.getElementById('grid');
      var cards = Array.prototype.slice.call(grid.querySelectorAll('.card'));
      var chipsEl = document.getElementById('chips');
      var chips = chipsEl ? Array.prototype.slice.call(chipsEl.querySelectorAll('.chip')) : [];
      var q = document.getElementById('q');
      // Touch devices have no "/" key shortcut to advertise (#399).
      if (q && window.matchMedia && window.matchMedia('(hover: none)').matches) {
        q.placeholder = 'Search the gallery';
      }
      var qClear = document.getElementById('qClear');
      var count = document.getElementById('count');
      var noResults = document.getElementById('noResults');
      var resetFilters = document.getElementById('resetFilters');
      var densityBtns = Array.prototype.slice.call(document.querySelectorAll('[data-density]'));
      var kindBtns = Array.prototype.slice.call(document.querySelectorAll('[data-kind-filter]'));
      var catRow = document.getElementById('cats');
      var catBtns = Array.prototype.slice.call(document.querySelectorAll('[data-cat-filter]'));
      var CATS = catBtns.map(function (b) { return b.getAttribute('data-cat-filter'); });
      var sortSel = document.getElementById('sort');
      var filtersEl = document.getElementById('filters');
      var filtersToggle = document.getElementById('filtersToggle');
      var toTop = document.getElementById('toTop');
      var total = cards.length;
      var COUNT_LABEL = '__COUNT_LABEL__';
      var LS_KEY = 'bdt-gallery-density';
      // Read by detail pages: the Gallery crumb returns here, and the pager
      // walks the reader's filtered order instead of the full gallery.
      var SS_HASH = 'bdt-gallery-hash', SS_ORDER = 'bdt-gallery-order';
      var KINDS = ['', 'examples', 'showcase'];
      var SORTS = ['default', 'az', 'kind', 'cat'];
      var reduced = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

      // data-search holds title, slug, teaches, tags and category. Each
      // query word must appear somewhere in it (AND), in any order.
      var haystacks = cards.map(function (c) { return c.getAttribute('data-search') || ''; });
      var cardTags = cards.map(function (c) { return (c.getAttribute('data-tags') || '').split(' '); });
      var knownTags = chips.map(function (c) { return c.getAttribute('data-tag') || ''; })
        .filter(function (t) { return t; });
      var state = { q: '', tags: [], kind: '', cat: '', sort: 'default', density: 'compact' };

      // Fade card renders in once decoded; images already complete (cache,
      // eager) are marked immediately so nothing stays invisible.
      cards.forEach(function (c) {
        var img = c.querySelector('.card-media img');
        if (!img) return;
        function done() { img.classList.add('is-loaded'); }
        if (img.complete) { done(); }
        else { img.addEventListener('load', done); img.addEventListener('error', done); }
      });

      function parseHash() {
        var out = {};
        location.hash.replace(/^#/, '').split('&').forEach(function (kv) {
          var i = kv.indexOf('=');
          if (i < 0) return;
          var k = kv.slice(0, i), v = kv.slice(i + 1);
          try { v = decodeURIComponent(v); } catch (e) {}
          if (k === 'q' || k === 'tag' || k === 'd' || k === 'k' || k === 'c' || k === 's') out[k] = v;
        });
        return out;
      }

      function filtered() {
        return !!(state.q.trim() || state.tags.length || state.kind || state.cat || state.sort !== 'default');
      }

      function remember() {
        try {
          sessionStorage.setItem(SS_HASH, location.hash);
          if (filtered()) {
            var order = [];
            Array.prototype.forEach.call(grid.children, function (c) {
              if (c.classList.contains('card') && !c.classList.contains('hidden')) {
                order.push(c.getAttribute('data-name'));
              }
            });
            sessionStorage.setItem(SS_ORDER, JSON.stringify(order));
          } else {
            sessionStorage.removeItem(SS_ORDER);
          }
        } catch (e) {}
      }

      // Discrete changes (chips, pills, kind, category, sort, reset) push a
      // history entry so Back undoes them; typing and density replace it.
      function writeHash(push) {
        var parts = [];
        if (state.q) parts.push('q=' + encodeURIComponent(state.q));
        if (state.tags.length) parts.push('tag=' + state.tags.map(encodeURIComponent).join(','));
        if (state.kind) parts.push('k=' + state.kind);
        if (state.cat) parts.push('c=' + state.cat);
        if (state.sort !== 'default') parts.push('s=' + state.sort);
        parts.push('d=' + state.density);
        var url = location.pathname + location.search + '#' + parts.join('&');
        if (push && url !== location.pathname + location.search + location.hash) history.pushState(null, '', url);
        else history.replaceState(null, '', url);
        remember();
      }
      var hashTimer = 0;
      function writeHashSoon() {
        clearTimeout(hashTimer);
        hashTimer = setTimeout(writeHash, 250);
      }

      function syncChips() {
        chips.forEach(function (c) {
          var t = c.getAttribute('data-tag') || '';
          var on = t ? state.tags.indexOf(t) !== -1 : state.tags.length === 0;
          c.classList.toggle('active', on);
          c.setAttribute('aria-pressed', on ? 'true' : 'false');
        });
      }

      function syncSeg(btns, attr, value) {
        btns.forEach(function (b) {
          var on = b.getAttribute(attr) === value;
          b.classList.toggle('active', on);
          b.setAttribute('aria-pressed', on ? 'true' : 'false');
        });
      }

      // The phone drawer button names how many filters are on, so a shared
      // filtered link never looks unfiltered with the drawer shut.
      function syncFiltersToggle() {
        var n = state.tags.length + (state.kind ? 1 : 0) + (state.cat ? 1 : 0) +
          (state.sort !== 'default' ? 1 : 0);
        filtersToggle.textContent = n ? 'Filters (' + n + ')' : 'Filters';
        filtersToggle.classList.toggle('has-active', n > 0);
      }

      // One removable pill per active filter, in the pinned search row.
      var pillsEl = document.getElementById('activeFilters');
      function syncPills() {
        if (!pillsEl) return;
        var items = state.tags.map(function (t) { return { label: t, drop: function () { state.tags.splice(state.tags.indexOf(t), 1); } }; });
        if (state.kind) items.push({ label: state.kind, drop: function () { state.kind = ''; } });
        if (state.cat) items.push({ label: state.cat, drop: function () { state.cat = ''; } });
        pillsEl.textContent = '';
        items.forEach(function (it) {
          var b = document.createElement('button');
          b.type = 'button'; b.className = 'pill';
          b.textContent = it.label + ' \u00d7';
          b.setAttribute('aria-label', 'Remove filter: ' + it.label);
          b.addEventListener('click', function () {
            it.drop(); syncChips(); applyFilters(); writeHash(true);
          });
          pillsEl.appendChild(b);
        });
        if (items.length > 1) {
          var all = document.createElement('button');
          all.type = 'button'; all.className = 'pill pill-clear'; all.textContent = 'Clear all';
          all.addEventListener('click', function () { if (resetFilters) resetFilters.click(); });
          pillsEl.appendChild(all);
        }
        pillsEl.hidden = items.length === 0;
      }

      // Topic chips collapse to two rows; "Show all N topics" reveals the rest.
      var moreBtn = document.getElementById('chipsMore');
      function chipClipped(el) {
        return el.getBoundingClientRect().bottom > chipsEl.getBoundingClientRect().bottom + 1;
      }
      function setChipsExpanded(on) {
        chipsEl.classList.toggle('expanded', on);
        moreBtn.setAttribute('aria-expanded', on ? 'true' : 'false');
        moreBtn.textContent = on ? 'Show fewer topics' : 'Show all ' + (chips.length - 1) + ' topics';
      }
      function measureChips() {
        if (!chipsEl || !moreBtn) return;
        var was = chipsEl.classList.contains('expanded');
        chipsEl.classList.remove('expanded');
        var over = chipsEl.scrollHeight > chipsEl.clientHeight + 2;
        if (was) chipsEl.classList.add('expanded');
        moreBtn.hidden = !over && !was;
      }
      if (chipsEl && moreBtn) {
        moreBtn.addEventListener('click', function () {
          setChipsExpanded(!chipsEl.classList.contains('expanded'));
        });
        // Keyboard focus never lands on a clipped chip: reveal the row first.
        chipsEl.addEventListener('focusin', function (e) {
          if (!chipsEl.classList.contains('expanded') && chipClipped(e.target)) setChipsExpanded(true);
        });
        window.addEventListener('resize', measureChips);
      }

      function applyDensity() {
        de.classList.toggle('density-compact', state.density === 'compact');
        syncSeg(densityBtns, 'data-density', state.density);
        try { localStorage.setItem(LS_KEY, state.density); } catch (e) {}
      }

      function applySort() {
        var order = cards.slice();
        if (state.sort === 'az') {
          order.sort(function (a, b) {
            var x = a.getAttribute('data-name'), y = b.getAttribute('data-name');
            return x < y ? -1 : x > y ? 1 : 0;
          });
        } else if (state.sort === 'kind' || state.sort === 'cat') {
          // Stable by gallery order within each group. Examples have no
          // category and sort first; showcase pieces follow CATEGORIES order.
          var rank = function (c) {
            if (c.getAttribute('data-kind') !== 'showcase') return -1;
            return state.sort === 'cat' ? CATS.indexOf(c.getAttribute('data-category')) : 0;
          };
          var pos = new Map(cards.map(function (c, i) { return [c, i]; }));
          order.sort(function (a, b) { return (rank(a) - rank(b)) || (pos.get(a) - pos.get(b)); });
        }
        order.forEach(function (c) { grid.appendChild(c); });
        sortSel.value = state.sort;
        syncFiltersToggle();
      }

      function applyFilters() {
        var words = state.q.trim().toLowerCase().split(/\s+/).filter(function (w) { return w; });
        var shown = 0;
        // Categories only partition showcase pieces; the examples view has
        // none, so it hides the row and drops any category left selected.
        if (state.kind === 'examples') state.cat = '';
        if (catRow) catRow.hidden = state.kind === 'examples';
        cards.forEach(function (card, i) {
          var kindOK = !state.kind || card.getAttribute('data-kind') === state.kind;
          var catOK = !state.cat || card.getAttribute('data-category') === state.cat;
          var tagOK = state.tags.every(function (t) { return cardTags[i].indexOf(t) !== -1; });
          var qOK = words.every(function (w) { return haystacks[i].indexOf(w) !== -1; });
          var show = kindOK && catOK && tagOK && qOK;
          card.classList.toggle('hidden', !show);
          if (show) shown++;
        });
        count.textContent = (words.length || state.tags.length || state.kind || state.cat) ? (shown + ' of ' + total) : COUNT_LABEL;
        noResults.hidden = shown !== 0;
        qClear.hidden = !state.q;
        syncSeg(kindBtns, 'data-kind-filter', state.kind);
        syncSeg(catBtns, 'data-cat-filter', state.cat);
        syncFiltersToggle();
        syncPills();
      }

      q.addEventListener('input', function () {
        state.q = q.value;
        applyFilters();
        writeHashSoon();
      });
      qClear.addEventListener('click', function () {
        q.value = ''; state.q = '';
        applyFilters(); writeHash(); q.focus();
      });
      // "All" clears the tag set; any other chip toggles itself, and
      // several active chips narrow the grid (AND, not OR).
      chips.forEach(function (chip) {
        chip.addEventListener('click', function () {
          var t = chip.getAttribute('data-tag') || '';
          if (!t) { state.tags = []; }
          else {
            var at = state.tags.indexOf(t);
            if (at === -1) state.tags.push(t); else state.tags.splice(at, 1);
          }
          syncChips(); applyFilters(); writeHash(true);
        });
      });
      // The chip row is one toolbar tab stop; arrows, Home and End move
      // within it (roving tabindex) instead of 35 separate Tab presses.
      if (chips.length) {
        var roving = 0;
        function rove(i) {
          chips[roving].tabIndex = -1;
          roving = (i + chips.length) % chips.length;
          chips[roving].tabIndex = 0;
        }
        chips.forEach(function (c, i) {
          c.tabIndex = i === 0 ? 0 : -1;
          c.addEventListener('focus', function () { rove(i); });
        });
        chipsEl.addEventListener('keydown', function (e) {
          var i = chips.indexOf(document.activeElement);
          if (i === -1) return;
          var to = e.key === 'ArrowRight' ? i + 1 : e.key === 'ArrowLeft' ? i - 1 :
            e.key === 'Home' ? 0 : e.key === 'End' ? chips.length - 1 : null;
          if (to === null) return;
          e.preventDefault();
          rove(to);
          chips[roving].focus();
          chips[roving].scrollIntoView({ block: 'nearest', inline: 'nearest' });
        });
      }
      kindBtns.forEach(function (b) {
        b.addEventListener('click', function () {
          state.kind = b.getAttribute('data-kind-filter');
          applyFilters(); writeHash(true);
        });
      });
      // A category only exists among showcase pieces, so picking one moves
      // the kind control to Showcase instead of leaving "All" lit.
      catBtns.forEach(function (b) {
        b.addEventListener('click', function () {
          state.cat = b.getAttribute('data-cat-filter');
          if (state.cat) state.kind = 'showcase';
          applyFilters(); writeHash(true);
        });
      });
      sortSel.addEventListener('change', function () {
        state.sort = SORTS.indexOf(sortSel.value) !== -1 ? sortSel.value : 'default';
        applySort(); writeHash(true);
      });
      densityBtns.forEach(function (b) {
        b.addEventListener('click', function () {
          state.density = b.getAttribute('data-density');
          applyDensity(); writeHash();
        });
      });
      resetFilters.addEventListener('click', function () {
        state.q = ''; state.tags = []; state.kind = ''; state.cat = ''; state.sort = 'default';
        q.value = '';
        syncChips(); applySort(); applyFilters(); writeHash(true); q.focus();
      });
      filtersToggle.addEventListener('click', function () {
        var open = filtersEl.classList.toggle('open');
        document.querySelector('.controls').classList.toggle('open', open);
        filtersToggle.setAttribute('aria-expanded', open ? 'true' : 'false');
      });

      document.addEventListener('keydown', function (e) {
        if (e.ctrlKey || e.altKey || e.metaKey) return;
        var ae = document.activeElement;
        var typing = ae && /^(INPUT|TEXTAREA|SELECT)$/.test(ae.tagName);
        if (e.key === '/' && !typing) {
          e.preventDefault();
          q.focus();
          q.select();
        } else if (e.key === 'Escape' && ae === q) {
          q.value = ''; state.q = '';
          applyFilters(); writeHash(); q.blur();
        }
      });

      function onScroll() { toTop.classList.toggle('show', window.scrollY > 600); }
      window.addEventListener('scroll', onScroll, { passive: true });
      onScroll();
      toTop.addEventListener('click', function () {
        window.scrollTo({ top: 0, behavior: reduced ? 'auto' : 'smooth' });
      });

      // Restore state from the URL hash; density falls back to localStorage.
      function restore() {
        // #check-only (the landing page links it) is an anchor, not filter state.
        var co = document.getElementById('check-only');
        if (co && location.hash === '#check-only') co.open = true;
        var h = parseHash();
        state.q = h.q || '';
        state.kind = KINDS.indexOf(h.k) !== -1 ? h.k : '';
        state.cat = h.c && CATS.indexOf(h.c) !== -1 ? h.c : '';
        state.sort = SORTS.indexOf(h.s) !== -1 ? h.s : 'default';
        state.tags = [];
        // Tags arrive comma-separated. "showcase" is the kind filter now, not
        // a chip, but older links still say #tag=showcase. A tag no chip
        // knows would silently show zero cards, so it is dropped.
        (h.tag || '').split(',').forEach(function (t) {
          if (t === 'showcase') { state.kind = 'showcase'; }
          else if (knownTags.indexOf(t) !== -1 && state.tags.indexOf(t) === -1) { state.tags.push(t); }
        });
        if (state.cat) state.kind = 'showcase';
        if (h.d === 'compact' || h.d === 'detailed') state.density = h.d;
        else {
          try {
            var s = localStorage.getItem(LS_KEY);
            if (s === 'compact' || s === 'detailed') state.density = s;
          } catch (e) {}
        }
        q.value = state.q;
        syncChips();
        // A deep-linked tag may sit off-screen in the chip scroll strip.
        var firstOn = chipsEl && chipsEl.querySelector('.chip.active[data-tag]:not([data-tag=""])');
        measureChips();
        if (firstOn && moreBtn && chipClipped(firstOn)) setChipsExpanded(true);
        applyDensity();
        applySort();
        applyFilters();
        remember();
      }
      // The header's Examples / Showcase links only change the hash here.
      window.addEventListener('hashchange', restore);
      restore();
    })();
