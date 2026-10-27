(function () {
  "use strict";

  // Product gallery: swap main image from thumbnails.
  document.querySelectorAll("[data-gallery]").forEach(function (gallery) {
    var main = gallery.querySelector("[data-gallery-main]");
    var thumbs = gallery.querySelectorAll("[data-gallery-thumb]");
    thumbs.forEach(function (thumb) {
      thumb.addEventListener("click", function () {
        if (!main) return;
        main.src = thumb.dataset.src;
        main.alt = thumb.dataset.alt || "";
        thumbs.forEach(function (t) {
          t.classList.toggle("border-ink", t === thumb);
          t.classList.toggle("border-transparent", t !== thumb);
        });
      });
    });
  });

  // Variant picker: live price, stock status, and quantity limit.
  document.querySelectorAll("[data-variant-form]").forEach(function (form) {
    var status = form.querySelector("[data-stock-status]");
    var qty = form.querySelector("[data-qty]");
    var price = document.querySelector("[data-price]");
    function update(input) {
      var stock = parseInt(input.dataset.stock, 10) || 0;
      if (price && input.dataset.price) price.textContent = input.dataset.price;
      if (qty) {
        qty.max = stock;
        if (parseInt(qty.value, 10) > stock) qty.value = stock;
      }
      if (status) {
        var dot = input.dataset.low ? "bg-amber-500" : "bg-emerald-500";
        var text = input.dataset.low ? "Only " + stock + " left" : "In stock, ships in 2–4 days";
        status.innerHTML = '<span class="h-2 w-2 rounded-full ' + dot + '"></span> ' + text;
      }
    }
    form.querySelectorAll('input[name="variant"]').forEach(function (input) {
      input.addEventListener("change", function () { update(input); });
    });
  });

  // Auto-submit (sort dropdown, cart quantity).
  document.querySelectorAll("[data-autosubmit]").forEach(function (el) {
    el.addEventListener("change", function () { el.form && el.form.requestSubmit(); });
  });

  // Cart +/- steppers.
  document.querySelectorAll("[data-step]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var input = btn.form.querySelector('input[name="quantity"]');
      var max = parseInt(input.max, 10);
      var next = (parseInt(input.value, 10) || 0) + parseInt(btn.dataset.step, 10);
      if (!isNaN(max)) next = Math.min(next, max);
      input.value = Math.max(0, next);
      btn.form.requestSubmit();
    });
  });

  // Checkout: live total from shipping choice.
  var checkout = document.querySelector("[data-checkout]");
  if (checkout) {
    var subEl = checkout.querySelector("[data-subtotal]");
    var shipOut = checkout.querySelector("[data-shipping-out]");
    var totalOut = checkout.querySelector("[data-total-out]");
    var symbol = (subEl.textContent.match(/^[^\d]*/) || [""])[0];
    var subtotal = parseFloat(subEl.dataset.subtotal);
    var fmt = function (n) {
      return symbol + n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    };
    var refresh = function () {
      var picked = checkout.querySelector('input[name="shipping_method"]:checked');
      if (!picked) return;
      var ship = parseFloat(picked.dataset.shippingPrice);
      shipOut.textContent = ship ? picked.dataset.shippingLabel : "Free";
      totalOut.textContent = fmt(subtotal + ship);
    };
    checkout.querySelectorAll('input[name="shipping_method"]').forEach(function (r) {
      r.addEventListener("change", refresh);
    });
    refresh();
    var payBtn = checkout.querySelector("button:not([type=button])");
    var payLabel = payBtn ? payBtn.firstChild.textContent : "";
    checkout.addEventListener("submit", function () {
      if (payBtn) { payBtn.disabled = true; payBtn.firstChild.textContent = "Redirecting to Stripe… "; }
    });
    window.addEventListener("pageshow", function (e) {
      if (e.persisted && payBtn) { payBtn.disabled = false; payBtn.firstChild.textContent = payLabel; }
    });
  }

  // Copy link.
  document.querySelectorAll("[data-copy]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      navigator.clipboard.writeText(btn.dataset.copy).then(function () {
        var label = btn.textContent;
        btn.textContent = "Copied ✓";
        setTimeout(function () { btn.textContent = label; }, 1600);
      });
    });
  });

  // Dismissible flash messages.
  document.querySelectorAll("[data-dismiss]").forEach(function (btn) {
    btn.addEventListener("click", function () { btn.closest("[data-dismissible]").remove(); });
  });

  document.querySelectorAll("[data-dismissible]").forEach(function (el) {
    setTimeout(function () { el.remove(); }, 6000);
  });

  // Close mobile nav when a link is tapped.
  var mobileNav = document.querySelector("[data-mobile-nav]");
  if (mobileNav) {
    mobileNav.querySelectorAll("a").forEach(function (a) {
      a.addEventListener("click", function () { mobileNav.removeAttribute("open"); });
    });
  }

  // Blog photo lightbox: click any article image; arrows/keys move through the post's photos.
  var lightbox = document.querySelector("[data-lightbox-dialog]");
  if (lightbox && lightbox.showModal) {
    var photos = Array.prototype.slice.call(document.querySelectorAll("[data-zoom], [data-lightbox] img"));
    var lbImg = lightbox.querySelector("[data-lightbox-img]");
    var lbCaption = lightbox.querySelector("[data-lightbox-caption]");
    var current = 0;
    var show = function (i) {
      current = (i + photos.length) % photos.length;
      var img = photos[current];
      var fig = img.closest("figure");
      var cap = fig && fig.querySelector("figcaption");
      lbImg.src = img.currentSrc || img.src;
      lbImg.alt = img.alt;
      lbCaption.textContent = cap ? cap.textContent : "";
    };
    photos.forEach(function (img, i) {
      img.style.cursor = "zoom-in";
      img.addEventListener("click", function () { show(i); lightbox.showModal(); });
    });
    var multi = photos.length > 1;
    var prevBtn = lightbox.querySelector("[data-lightbox-prev]");
    var nextBtn = lightbox.querySelector("[data-lightbox-next]");
    if (multi) {
      prevBtn.addEventListener("click", function () { show(current - 1); });
      nextBtn.addEventListener("click", function () { show(current + 1); });
    } else {
      prevBtn.remove();
      nextBtn.remove();
    }
    lightbox.querySelector("[data-lightbox-close]").addEventListener("click", function () { lightbox.close(); });
    lightbox.addEventListener("click", function (e) {
      if (e.target === lightbox || e.target === lbImg.parentNode) lightbox.close();
    });
    lightbox.addEventListener("keydown", function (e) {
      if (!multi) return;
      if (e.key === "ArrowRight") show(current + 1);
      if (e.key === "ArrowLeft") show(current - 1);
    });
  }

  // Store rows: arrow buttons scroll the strip; each hides at its end (both hide when everything fits).
  document.querySelectorAll("[data-carousel]").forEach(function (row) {
    var track = row.querySelector("[data-carousel-track]");
    var prev = row.querySelector("[data-carousel-prev]");
    var next = row.querySelector("[data-carousel-next]");
    if (!track || !prev || !next) return;
    var sync = function () {
      prev.disabled = track.scrollLeft <= 4;
      next.disabled = track.scrollLeft + track.clientWidth >= track.scrollWidth - 4;
    };
    var step = function (dir) { track.scrollBy({ left: dir * track.clientWidth * 0.85, behavior: "smooth" }); };
    prev.addEventListener("click", function () { step(-1); });
    next.addEventListener("click", function () { step(1); });
    track.addEventListener("scroll", sync, { passive: true });
    window.addEventListener("resize", sync);
    sync();
  });

  // Eased scroll to an on-page section (home "scroll down" arrow). Stops if the visitor scrolls themselves.
  document.querySelectorAll("a[data-smooth-scroll]").forEach(function (link) {
    link.addEventListener("click", function (e) {
      var target = document.querySelector(link.getAttribute("href"));
      if (!target) return;
      e.preventDefault();
      var offset = parseFloat(getComputedStyle(target).scrollMarginTop) || 0;
      var start = window.scrollY;
      var end = Math.max(0, target.getBoundingClientRect().top + start - offset);
      var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      var finish = function () {
        target.setAttribute("tabindex", "-1");
        target.focus({ preventScroll: true });
      };
      if (reduce) { window.scrollTo(0, end); finish(); return; }

      var duration = Math.min(1200, Math.max(600, Math.abs(end - start) * 0.9));
      var ease = function (t) { return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2; };
      var began = null;
      var cancelled = false;
      var cancel = function () { cancelled = true; };
      window.addEventListener("wheel", cancel, { passive: true, once: true });
      window.addEventListener("touchstart", cancel, { passive: true, once: true });
      var step = function (now) {
        if (cancelled) return;
        if (began === null) began = now;
        var t = Math.min(1, (now - began) / duration);
        window.scrollTo(0, start + (end - start) * ease(t));
        if (t < 1) { requestAnimationFrame(step); } else {
          window.removeEventListener("wheel", cancel);
          window.removeEventListener("touchstart", cancel);
          finish();
        }
      };
      requestAnimationFrame(step);
    });
  });

  // Home video: pause/play button. Visitors who ask for reduced motion get the still image until they press play.
  var heroVideo = document.querySelector("[data-hero-video]");
  var heroToggle = document.querySelector("[data-hero-toggle]");
  if (heroVideo && heroToggle) {
    var syncToggle = function () {
      var paused = heroVideo.paused;
      heroToggle.setAttribute("aria-pressed", paused ? "true" : "false");
      heroToggle.setAttribute("aria-label", paused ? "Play video" : "Pause video");
      heroToggle.querySelector("[data-icon-pause]").classList.toggle("hidden", paused);
      heroToggle.querySelector("[data-icon-play]").classList.toggle("hidden", !paused);
    };
    if (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      heroVideo.removeAttribute("autoplay");
      heroVideo.pause();
    }
    heroToggle.addEventListener("click", function () {
      if (heroVideo.paused) { heroVideo.play(); } else { heroVideo.pause(); }
    });
    heroVideo.addEventListener("play", syncToggle);
    heroVideo.addEventListener("pause", syncToggle);
    syncToggle();
  }

  // Sticky subscribe button: focus the email field on open; close with ×, Escape, or a click elsewhere.
  var popup = document.querySelector("[data-subscribe-popup]");
  if (popup) {
    popup.addEventListener("toggle", function () {
      if (popup.open) popup.querySelector('input[type="email"]').focus();
    });
    popup.querySelector("[data-subscribe-close]").addEventListener("click", function () { popup.open = false; });
    document.addEventListener("keydown", function (e) { if (e.key === "Escape") popup.open = false; });
    document.addEventListener("click", function (e) { if (popup.open && !popup.contains(e.target)) popup.open = false; });
  }

  // Transparent header over the home hero turns solid once scrolled or when the menu opens.
  var overlayHeader = document.querySelector("[data-header][data-overlay]");
  if (overlayHeader) {
    var syncHeader = function () {
      var solid = window.scrollY > 40 || (mobileNav && mobileNav.open);
      overlayHeader.dataset.scrolled = solid ? "true" : "false";
    };
    window.addEventListener("scroll", syncHeader, { passive: true });
    if (mobileNav) mobileNav.addEventListener("toggle", syncHeader);
    syncHeader();
  }
})();
