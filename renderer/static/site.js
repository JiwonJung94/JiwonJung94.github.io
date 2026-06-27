(function () {
  "use strict";
  var LS_KEY = "book-lang";
  function getLang(def) { try { return localStorage.getItem(LS_KEY) || def; } catch (e) { return def; } }
  function setLang(l) { try { localStorage.setItem(LS_KEY, l); } catch (e) {} }
  function esc(s) { var d = document.createElement("div"); d.textContent = s == null ? "" : s; return d.innerHTML; }
  function viewsLabel(lang, n) {
    var s = (n || 0).toLocaleString();
    if (lang === "ko") return "조회 " + s;
    if (lang === "vi") return s + " lượt xem";
    return s + " views";
  }

  var themeBtn = document.getElementById("theme-toggle");
  if (themeBtn) {
    themeBtn.addEventListener("click", function () {
      var next = document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark";
      document.documentElement.setAttribute("data-theme", next);
      try { localStorage.setItem("theme", next); } catch (e) {}
    });
  }

  var shareBtns = document.querySelectorAll(".share-btn");
  if (shareBtns.length) {
    var SH = { ko: { s: "공유", c: "링크 복사됨" }, en: { s: "Share", c: "Link copied" }, vi: { s: "Chia sẻ", c: "Đã sao chép" } };
    var sl = SH[document.documentElement.getAttribute("lang")] || SH.en;
    Array.prototype.forEach.call(shareBtns, function (btn) {
      btn.textContent = sl.s;
      btn.addEventListener("click", function () {
        if (navigator.share) { navigator.share({ title: document.title, url: location.href }).catch(function () {}); return; }
        if (navigator.clipboard) {
          navigator.clipboard.writeText(location.href).then(function () {
            btn.textContent = sl.c; setTimeout(function () { btn.textContent = sl.s; }, 1500);
          }).catch(function () {});
        }
      });
    });
  }

  var progress = document.getElementById("read-progress");
  if (progress) {
    var updateProgress = function () {
      var max = document.documentElement.scrollHeight - window.innerHeight;
      progress.style.width = (max > 0 ? (window.scrollY / max) * 100 : 0) + "%";
    };
    addEventListener("scroll", updateProgress, { passive: true });
    addEventListener("resize", updateProgress);
    updateProgress();
  }

  var pageSel = document.querySelector('select.lang-select[data-kind="page"]');
  if (pageSel) {

    setLang(document.documentElement.getAttribute("lang"));
    pageSel.addEventListener("change", function () {
      var opt = pageSel.options[pageSel.selectedIndex];
      setLang(opt.getAttribute("data-code"));
      window.location.href = opt.value;
    });
  }

  if (window.__VIEWS__ && window.__VIEWS__.url) {
    var V = window.__VIEWS__;
    var q = V.url + "?book=" + encodeURIComponent(V.book) +
      "&slug=" + encodeURIComponent(V.slug) + "&lang=" + encodeURIComponent(V.lang) +
      "&locales=" + encodeURIComponent((V.locales || []).join(",")) + "&hit=1";
    fetch(q).then(function (r) { return r.json(); }).then(function (d) {
      var el = document.getElementById("views");
      if (el && typeof d.page === "number") el.textContent = viewsLabel(V.lang, d.page);
    }).catch(function () {});
  }

  var navCollapse = document.getElementById("nav-collapse");
  if (navCollapse) {
    var NK = "nav-collapsed";
    navCollapse.addEventListener("click", function () {
      var c = !document.body.classList.contains("nav-collapsed");
      try { localStorage.setItem(NK, c ? "1" : "0"); } catch (e) {}
      document.body.classList.toggle("nav-collapsed", c);
    });
    var stored = null;
    try { stored = localStorage.getItem(NK); } catch (e) {}
    document.body.classList.toggle("nav-collapsed", stored === "1");
  }

  var shelf = document.getElementById("shelf");
  if (shelf && window.__SITE__) {
    var site = window.__SITE__;
    var langSel = document.getElementById("lang-select");
    var searchInput = document.getElementById("search");
    var results = document.getElementById("results");
    var indexCache = null;

    var UI = {
      ko: { search: "제목·내용 검색…", none: "검색 결과가 없습니다.", empty: "책이 없습니다.",
            count: function (n) { return n + "권"; } },
      en: { search: "Search titles and contents…", none: "No results.", empty: "No books.",
            count: function (n) { return n + (n === 1 ? " book" : " books"); } },
      vi: { search: "Tìm tiêu đề và nội dung…", none: "Không có kết quả.", empty: "Chưa có sách.",
            count: function (n) { return n + " sách"; } },
    };
    function ui() { return UI[lang] || UI[site.defaultLang] || UI.en; }

    var lang = getLang(site.defaultLang);
    if (site.langs.indexOf(lang) < 0) lang = site.defaultLang;

    site.langs.forEach(function (l) {
      var op = document.createElement("option");
      op.value = l; op.textContent = site.langNames[l] || l;
      if (l === lang) op.selected = true;
      langSel.appendChild(op);
    });

    function pick(map, def) { return (map && (map[lang] || map[def])) || ""; }
    function bookLocale(b) { return b.locales.indexOf(lang) >= 0 ? lang : b.default; }
    function bookLink(b) { return b.id + "/" + bookLocale(b) + "/" + b.first; }

    function snippetHTML(text, q) {
      var i = text.toLowerCase().indexOf(q);
      if (i < 0) return "";
      var s = Math.max(0, i - 40), e = Math.min(text.length, i + q.length + 70);
      return (s > 0 ? "…" : "") + esc(text.slice(s, i)) +
        "<mark>" + esc(text.slice(i, i + q.length)) + "</mark>" +
        esc(text.slice(i + q.length, e)) + (e < text.length ? "…" : "");
    }

    function applyChrome(visibleCount) {
      document.documentElement.setAttribute("lang", lang);
      var st = document.getElementById("site-title");
      var ss = document.getElementById("site-subtitle");
      if (st && site.title) st.textContent = pick(site.title, site.defaultLang);
      if (ss) {
        var sub = pick(site.subtitle, site.defaultLang);
        ss.textContent = sub; ss.style.display = sub ? "" : "none";
      }
      searchInput.placeholder = ui().search;
    }

    function card(b) {
      var title = esc(pick(b.title, b.default));
      var cov = b.cover
        ? '<span class="cover" style="background-image:url(\'' + b.id + "/" + b.cover + '\')"></span>'
        : '<span class="cover placeholder"><span class="cover-initial">' + esc(pick(b.title, b.default).slice(0, 1)) + "</span></span>";
      var author = pick(b.author, b.default);
      var desc = pick(b.description, b.default);
      var cr = pick(b.copyright, b.default);
      var baRow = (author || b.contact)
        ? '<span class="ba-row">' +
            (author ? '<span class="ba">' + esc(author) + "</span>" : "") +
            (b.contact ? '<a class="contact" href="mailto:' + esc(b.contact) + '">Contact</a>' : "") +
          "</span>"
        : "";
      return '<div class="book-card">' +
        '<a class="card-link" href="' + bookLink(b) + '" aria-label="' + title + '"></a>' + cov +
        '<span class="card-body"><span class="bt">' + title + "</span>" + baRow +
        (desc ? '<span class="bd">' + esc(desc) + "</span>" : "") +
        '<span class="card-foot">' +
          (cr ? '<span class="bc">' + esc(cr) + "</span>" : "") +
          (site.viewsUrl ? '<span class="views" data-book="' + esc(b.id) + '"></span>' : "") +
        "</span>" +
        "</span></div>";
    }

    function fillViews() {
      if (!site.viewsUrl) return;
      var els = shelf.querySelectorAll(".views[data-book]");
      Array.prototype.forEach.call(els, function (el) {
        var id = el.getAttribute("data-book");
        fetch(site.viewsUrl + "?book=" + encodeURIComponent(id))
          .then(function (r) { return r.json(); })
          .then(function (d) { if (typeof d.book === "number") el.textContent = viewsLabel(lang, d.book); })
          .catch(function () {});
      });
    }

    function renderShelf(books) {
      shelf.innerHTML = books.map(card).join("") || '<p class="noresult">' + ui().empty + "</p>";
      fillViews();
    }

    function loadIndex(cb) {
      if (indexCache) return cb(indexCache);
      fetch("search-index.json").then(function (r) { return r.json(); })
        .then(function (j) { indexCache = j; cb(j); }).catch(function () { cb(null); });
    }

    function runSearch(q) {
      q = (q || "").trim().toLowerCase();
      results.innerHTML = "";
      if (!q) { renderShelf(site.books); applyChrome(site.books.length); return; }
      loadIndex(function (idx) {
        if (!idx) { return; }
        var matched = [];
        idx.books.forEach(function (b) {
          var meta = site.books.filter(function (x) { return x.id === b.id; })[0] || b;
          var titleHit = pick(b.title, b.default).toLowerCase().indexOf(q) >= 0 ||
            pick(b.description, b.default).toLowerCase().indexOf(q) >= 0;
          var hits = [];
          b.pages.forEach(function (p) {
            var pt = (p.title && (p.title[lang] || p.title[b.default])) || "";
            var bd = (p.text && (p.text[lang] || p.text[b.default])) || "";
            var inBody = bd.toLowerCase().indexOf(q) >= 0;
            var inTitle = pt.toLowerCase().indexOf(q) >= 0;
            if (inTitle || inBody) {
              hits.push({
                title: pt,
                url: b.id + "/" + bookLocale(meta) + "/" + p.slug + ".html",
                snippet: inBody ? snippetHTML(bd, q) : "<mark>" + esc(pt) + "</mark>",
              });
            }
          });
          if (titleHit || hits.length) matched.push({ meta: meta, hits: hits });
        });
        renderShelf(matched.map(function (m) { return m.meta; }));
        applyChrome(matched.length);
        matched.forEach(function (m) {
          if (!m.hits.length) return;
          var html = "<h3>" + esc(pick(m.meta.title, m.meta.default)) + "</h3><ul>" +
            m.hits.slice(0, 8).map(function (h) {
              return '<li><a href="' + h.url + '">' + esc(h.title) + "</a>" +
                (h.snippet ? '<span class="snip">' + h.snippet + "</span>" : "") + "</li>";
            }).join("") + "</ul>";
          var sec = document.createElement("div");
          sec.className = "result-book";
          sec.innerHTML = html;
          results.appendChild(sec);
        });
        if (!matched.length) results.innerHTML = '<p class="noresult">' + ui().none + "</p>";
      });
    }

    langSel.addEventListener("change", function () { lang = langSel.value; setLang(lang); runSearch(searchInput.value); });
    searchInput.addEventListener("input", function () { runSearch(searchInput.value); });
    renderShelf(site.books);
    applyChrome(site.books.length);
  }
})();
