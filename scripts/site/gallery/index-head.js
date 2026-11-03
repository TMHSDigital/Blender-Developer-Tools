
  <script>
    (function () {
      var de = document.documentElement;
      de.classList.add('js');
      var d = 'compact';
      var m = location.hash.match(/(?:^|[#&])d=(compact|detailed)/);
      if (m) { d = m[1]; }
      else {
        try {
          var s = localStorage.getItem('bdt-gallery-density');
          if (s === 'compact' || s === 'detailed') d = s;
        } catch (e) {}
      }
      if (d === 'compact') de.classList.add('density-compact');
    })();
  </script>