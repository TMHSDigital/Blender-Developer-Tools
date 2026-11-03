
    (function () {
      var hero = document.getElementById('heroZoom');
      var box = document.getElementById('lightbox');
      if (hero && box) {
        // <dialog>.showModal() traps focus, closes on Escape, and returns
        // focus to the hero button on close. The dialog fills the viewport,
        // so a click whose target is the dialog itself is a backdrop click.
        var full = box.querySelector('img');
        var nativeBtn = document.getElementById('lightboxNative');
        function setNative(on) {
          box.classList.toggle('native', on);
          nativeBtn.setAttribute('aria-pressed', on ? 'true' : 'false');
          nativeBtn.textContent = on ? 'Fit to screen' : 'Actual size';
        }
        hero.addEventListener('click', function () { setNative(false); box.showModal(); });
        box.addEventListener('click', function (e) { if (e.target === box) box.close(); });
        document.getElementById('lightboxClose').addEventListener('click', function () { box.close(); });
        full.addEventListener('click', function () { setNative(!box.classList.contains('native')); });
        nativeBtn.addEventListener('click', function () { setNative(!box.classList.contains('native')); });
      }

      var srStatus = document.getElementById('srStatus');
      function announce(msg) {
        srStatus.textContent = '';
        setTimeout(function () { srStatus.textContent = msg; }, 50);
      }

      // Back to the gallery with the filters the reader left it with, and
      // page through that filtered order when there is one (both written by
      // the gallery index into sessionStorage; absent, the static links stay).
      var here = location.pathname.replace(/[/]$/, '').split('/').pop();
      try {
        var savedHash = sessionStorage.getItem('bdt-gallery-hash');
        var crumb = document.getElementById('crumbGallery');
        if (crumb && savedHash) crumb.setAttribute('href', '../' + savedHash);
        var order = JSON.parse(sessionStorage.getItem('bdt-gallery-order') || 'null');
        var at = order ? order.indexOf(here) : -1;
        if (at !== -1) {
          Array.prototype.forEach.call(document.querySelectorAll('.pager'), function (nav) {
            function slot(name, rel) {
              if (!name) return document.createElement('span');
              var a = document.createElement('a');
              a.rel = rel; a.href = '../' + name + '/';
              a.setAttribute('aria-label', (rel === 'prev' ? 'Previous' : 'Next') + ' in your filter: ' + name);
              a.innerHTML = rel === 'prev'
                ? '<span aria-hidden="true">&larr;</span> ' + name
                : name + ' <span aria-hidden="true">&rarr;</span>';
              return a;
            }
            var pos = nav.querySelector('.pager-pos');
            var keys = pos.querySelector('.pager-keys');
            nav.replaceChild(slot(order[at - 1], 'prev'), nav.firstElementChild);
            nav.replaceChild(slot(order[at + 1], 'next'), nav.lastElementChild);
            pos.textContent = (at + 1) + ' of ' + order.length + ' in your filter';
            if (keys) pos.appendChild(keys);
            nav.setAttribute('aria-label', 'Your filtered gallery');
          });
        }
      } catch (e) {}

      // Clipboard API first; execCommand for non-secure origins (file://,
      // plain-http previews) where navigator.clipboard is undefined.
      function copyText(text) {
        if (navigator.clipboard && window.isSecureContext) {
          return navigator.clipboard.writeText(text);
        }
        return new Promise(function (resolve, reject) {
          var ta = document.createElement('textarea');
          ta.value = text;
          ta.setAttribute('readonly', '');
          ta.style.position = 'fixed'; ta.style.opacity = '0';
          document.body.appendChild(ta);
          ta.select();
          var ok = false;
          try { ok = document.execCommand('copy'); } catch (e) {}
          document.body.removeChild(ta);
          if (ok) { resolve(); } else { reject(); }
        });
      }
      function wireCopy(btn, getText) {
        btn.addEventListener('click', function () {
          copyText(getText()).then(function () {
            btn.textContent = 'Copied'; btn.classList.add('done'); announce('Copied to clipboard');
          }, function () {
            btn.textContent = 'Copy failed'; btn.classList.add('fail'); announce('Copy failed');
          }).then(function () {
            setTimeout(function () {
              btn.textContent = 'Copy'; btn.classList.remove('done', 'fail');
            }, 1600);
          });
        });
      }
      [['copyRun', 'runCmd'], ['copyFalsify', 'falsifyCmd']].forEach(function (ids) {
        var copy = document.getElementById(ids[0]);
        if (copy) {
          wireCopy(copy, function () { return document.getElementById(ids[1]).textContent; });
        }
      });
      Array.prototype.forEach.call(document.querySelectorAll('.md pre'), function (block) {
        var wrap = block;
        if (block.tagName === 'PRE') {
          wrap = document.createElement('div');
          block.parentNode.insertBefore(wrap, block);
          wrap.appendChild(block);
        }
        wrap.classList.add('codewrap');
        var btn = document.createElement('button');
        btn.type = 'button'; btn.className = 'copy-btn'; btn.textContent = 'Copy';
        var src = block.tagName === 'PRE' ? block : block.querySelector('.code-lines');
        btn.setAttribute('aria-label', 'Copy code');
        wireCopy(btn, function () { return src.textContent; });
        wrap.appendChild(btn);
      });

      // Left/right arrows page between entries, but only when nothing has
      // focus and nothing is selected: a focused control, a scrolled code
      // block, or a text selection keeps its own arrow keys. A click inside a
      // code block does not always move focus (or a selection), so also keep
      // the arrows when the last click landed in one that scrolls sideways
      // (#398).
      var lastPointer = null;
      document.addEventListener('pointerdown', function (e) { lastPointer = e.target; }, true);
      document.addEventListener('keydown', function (e) {
        if (e.ctrlKey || e.altKey || e.metaKey || e.shiftKey) return;
        if (box && box.open) return;
        var scroller = lastPointer && lastPointer.closest
          && lastPointer.closest('pre, .code-lines, .codewrap');
        if (scroller && scroller.scrollWidth > scroller.clientWidth) return;
        var ae = document.activeElement;
        if (ae && ae !== document.body && ae !== document.documentElement) return;
        var sel = window.getSelection && window.getSelection();
        if (sel && !sel.isCollapsed) return;
        var rel = e.key === 'ArrowLeft' ? 'prev' : e.key === 'ArrowRight' ? 'next' : '';
        if (!rel) return;
        var a = document.querySelector('.pager a[rel="' + rel + '"]');
        if (a) { location.href = a.href; }
      });
    })();
