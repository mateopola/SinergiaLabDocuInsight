/* =========================================================
   DocuInsight Landing · SinergIA Lab
   Scroll animations, nav behavior, smooth interactions
   ========================================================= */

(function () {
    'use strict';

    // --- Fade-in on scroll via IntersectionObserver ---
    const fadeEls = document.querySelectorAll('.fade-in-up');
    if ('IntersectionObserver' in window && fadeEls.length) {
        const io = new IntersectionObserver((entries) => {
            entries.forEach((entry) => {
                if (entry.isIntersecting) {
                    entry.target.classList.add('visible');
                    io.unobserve(entry.target);
                }
            });
        }, {
            threshold: 0.12,
            rootMargin: '0px 0px -80px 0px',
        });
        fadeEls.forEach((el) => io.observe(el));
    } else {
        // Fallback: show all
        fadeEls.forEach((el) => el.classList.add('visible'));
    }

    // --- Nav background on scroll ---
    const nav = document.getElementById('nav');
    if (nav) {
        const onScroll = () => {
            if (window.scrollY > 24) {
                nav.classList.add('scrolled');
            } else {
                nav.classList.remove('scrolled');
            }
        };
        window.addEventListener('scroll', onScroll, { passive: true });
        onScroll();
    }

    // --- Smooth scroll for anchor links (offset for fixed nav) ---
    document.querySelectorAll('a[href^="#"]').forEach((anchor) => {
        anchor.addEventListener('click', function (e) {
            const targetId = this.getAttribute('href');
            if (targetId === '#' || targetId.length < 2) return;
            const target = document.querySelector(targetId);
            if (!target) return;

            e.preventDefault();
            const offset = 80; // approx nav height
            const top = target.getBoundingClientRect().top + window.pageYOffset - offset;
            window.scrollTo({ top, behavior: 'smooth' });
        });
    });

    // --- Subtle parallax on hero abstract decoration ---
    const heroDecoration = document.querySelector('#hero svg')?.closest('div');
    if (heroDecoration && window.matchMedia('(min-width: 1024px)').matches) {
        let raf = null;
        window.addEventListener('scroll', () => {
            if (raf) return;
            raf = requestAnimationFrame(() => {
                const y = Math.min(window.scrollY * 0.15, 80);
                heroDecoration.style.transform = `translateY(${y}px)`;
                raf = null;
            });
        }, { passive: true });
    }

    // --- Console signature ---
    console.log('%cDocuInsight · SinergIA Lab', 'font-family:Space Grotesk;font-size:18px;font-weight:700;background:linear-gradient(90deg,#0C74C8,#FE6B23);color:white;padding:8px 16px;border-radius:6px;');
    console.log('%cHiperautomatización inteligente para procesos documentales empresariales.', 'color:#41444B;font-size:11px;');
})();
