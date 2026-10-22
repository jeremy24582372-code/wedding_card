(() => {
  'use strict';
  const cover = document.getElementById('cover-screen');
  const details = document.getElementById('invitation');
  const open = document.getElementById('open-invitation');
  const back = document.getElementById('back-to-cover');
  const dialog = document.getElementById('calendar-dialog');
  const addCalendar = document.getElementById('add-calendar');
  const google = document.getElementById('google-calendar');
  const downloadCalendar = document.getElementById('download-ics');
  const content = document.getElementById('site-content');
  const loader = document.getElementById('site-loading');
  const loadingMessage = document.getElementById('loading-message');
  const retryLoading = document.getElementById('retry-loading');
  const isDetails = () => location.hash === '#invitation';
  const showPage = (focus = false) => {
    const active = isDetails();
    if (dialog.open) dialog.close();
    cover.hidden = active;
    details.hidden = !active;
    document.title = `${active ? '婚宴資訊' : '婚禮邀請'}｜Jeremy & Yuri｜2027.01.23`;
    window.scrollTo({top: 0, behavior: 'instant'});
    if (focus) (active ? document.getElementById('details-title') : open).focus({preventScroll: true});
  };
  const goCover = () => {
    if (history.state?.weddingInvitation) {
      history.back();
    } else {
      history.replaceState(null, '', location.pathname + location.search);
      showPage(true);
    }
  };
  open.addEventListener('click', event => {
    event.preventDefault();
    if (!isDetails()) history.pushState({weddingInvitation: true}, '', '#invitation');
    showPage(true);
    void preloadDetails();
  });
  back.addEventListener('click', goCover);
  window.addEventListener('popstate', () => showPage(true));
  window.addEventListener('hashchange', () => showPage());
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && !dialog.open && isDetails()) goCover();
  });
  let touchStart;
  details.addEventListener('touchstart', event => {
    touchStart = event.touches.length === 1 ? {x: event.touches[0].clientX, y: event.touches[0].clientY} : null;
  }, {passive: true});
  details.addEventListener('touchend', event => {
    if (!touchStart || dialog.open || !event.changedTouches.length) return;
    const dx = event.changedTouches[0].clientX - touchStart.x;
    const dy = event.changedTouches[0].clientY - touchStart.y;
    touchStart = null;
    if (dx > 100 && dx > Math.abs(dy) * 2 && isDetails()) goCover();
  }, {passive: true});
  const calendarParams = new URLSearchParams({
    action: 'TEMPLATE',
    text: '謝僑育 & 佐藤友里 婚宴',
    dates: '20270123T033000Z/20270123T080000Z',
    details: '誠摯邀請您一同見證我們的幸福時刻。\n11:30 賓客入場\n12:00 午宴開席\n16:00 婚宴結束\n晶宴日光香頌（B2圓環廳）',
    location: '晶宴日光香頌（B2圓環廳），臺北市中山區民生東路三段8號',
    ctz: 'Asia/Taipei'
  });
  google.href = 'https://calendar.google.com/calendar/render?' + calendarParams.toString();
  // Warm every second-page image, including SVG lettering and the CSS paper.
  // Keep the Image objects alive so their decoded pixels can be reused.
  const preparedImages = [];
  const preloadImages = (sources, priority) => Promise.allSettled(
    Array.from(new Set(sources)).filter(Boolean).map(source =>
      new Promise((resolve, reject) => {
        const image = new Image();
        preparedImages.push(image);
        image.decoding = 'async';
        image.fetchPriority = priority;
        image.onload = async () => {
          try {
            if (image.decode) await image.decode();
            resolve();
          } catch (error) { reject(error); }
        };
        image.onerror = () => reject(new Error('Image could not load'));
        image.src = source;
      })
    )
  );
  let detailsReady;
  const preloadDetails = () => {
    if (detailsReady) return detailsReady;
    const sources = new Set([
      'assets/details-background.png',
      ...Array.from(details.querySelectorAll('img, image'), element =>
        element.getAttribute('src') || element.getAttribute('href'))
    ]);
    detailsReady = preloadImages(sources, 'low');
    return detailsReady;
  };
  // Reuse one in-memory calendar download; retain the original link on failure.
  const calendarFileURL = downloadCalendar.href;
  let calendarReady;
  const preloadCalendar = () => {
    if (!calendarReady) {
      calendarReady = (async () => {
        const response = await fetch(calendarFileURL, {cache: 'force-cache', credentials: 'same-origin'});
        if (!response.ok) return;
        const content = await response.text();
        if (!content.trimStart().startsWith('BEGIN:VCALENDAR')) return;
        downloadCalendar.href = URL.createObjectURL(new Blob([content], {type: 'text/calendar;charset=utf-8'}));
      })().catch(() => {});
    }
    return calendarReady;
  };
  addCalendar.addEventListener('click', () => {
    void preloadCalendar();
    dialog.showModal();
  });
  document.getElementById('close-dialog').addEventListener('click', () => dialog.close());
  dialog.addEventListener('click', event => {
    if (event.target !== dialog) return;
    const bounds = dialog.getBoundingClientRect();
    if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) dialog.close();
  });
  dialog.addEventListener('close', () => {if (isDetails()) addCalendar.focus({preventScroll: true});});
  google.addEventListener('click', () => dialog.close());
  downloadCalendar.addEventListener('click', () => dialog.close());
  retryLoading.addEventListener('click', () => location.reload());
  showPage();
  const coverReady = preloadImages([
    'assets/cover-background.png',
    ...Array.from(cover.querySelectorAll('img, image'), element =>
      element.getAttribute('src') || element.getAttribute('href'))
  ], 'high');
  const secondPageReady = preloadDetails();
  void secondPageReady.then(preloadCalendar);
  // Normal entry only waits for the cover, never for second-page downloads.
  const firstPageReady = isDetails()
    ? Promise.all([coverReady, secondPageReady]).then(results => results.flat())
    : coverReady;
  void firstPageReady.then(results => {
    if (results.some(result => result.status === 'rejected')) {
      loader.classList.add('has-error');
      loader.setAttribute('aria-busy', 'false');
      loadingMessage.textContent = '喜帖圖片載入失敗，請重新載入。';
      retryLoading.hidden = false;
      return;
    }
    content.hidden = false;
    content.removeAttribute('inert');
    content.setAttribute('aria-busy', 'false');
    loadingMessage.textContent = '喜帖載入完成';
    loader.setAttribute('aria-busy', 'false');
    loader.classList.add('is-complete');
    setTimeout(() => { loader.hidden = true; }, 350);
  });
})();
