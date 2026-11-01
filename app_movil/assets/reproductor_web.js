(() => {
  'use strict';
  if (location.href === 'about:blank') return;
  const token = __KAIROS_TOKEN__;
  let muted = __KAIROS_MUTED__;
  const attached = new WeakSet();
  let scheduled = false;
  let rootIsolated = false;
  function report(event) {
    try { KairosWebPlayer.postMessage(JSON.stringify({token, event})); } catch (_) {}
  }
  function fill(element) {
    for (const [key, value] of Object.entries({position:'fixed',inset:'0',width:'100vw',height:'100vh',
      margin:'0',padding:'0',border:'0',maxWidth:'none',maxHeight:'none',background:'black',zIndex:'1'})) {
      element.style.setProperty(key.replace(/[A-Z]/g, m => '-'+m.toLowerCase()), value, 'important');
    }
  }
  function isolate(target) {
    if (!document.body || !target) return;
    document.documentElement.style.background = 'black';
    document.documentElement.style.overflow = 'hidden';
    document.body.style.margin = '0';
    document.body.style.overflow = 'hidden';
    let branch = target;
    while (branch && branch !== document.body) {
      const parent = branch.parentElement;
      if (!parent) break;
      for (const sibling of parent.children) {
        if (sibling !== branch && !['SCRIPT','STYLE','LINK'].includes(sibling.tagName)) {
          sibling.style.setProperty('display', 'none', 'important');
        }
      }
      branch = parent;
    }
    fill(target);
    if (window === window.top && !rootIsolated) { rootIsolated = true; report('isolated'); }
    if (target.tagName === 'VIDEO') target.style.objectFit = 'contain';
    if (target.tagName === 'IFRAME') {
      target.setAttribute('allow', 'autoplay; fullscreen; encrypted-media; picture-in-picture');
      target.setAttribute('allowfullscreen', '');
    }
  }
  function tryPlay(video) {
    video.muted = muted;
    try { const playing = video.play(); if (playing) playing.catch(() => {}); } catch (_) {}
  }
  function scan() {
    scheduled = false;
    if (!document.body) return;
    const videos = Array.from(document.querySelectorAll('video'));
    const video = videos.find(v => v.readyState > 0) || videos[0];
    const frame = document.querySelector('#embedIframe, iframe[allowfullscreen], iframe[allow*="fullscreen"]') ||
      (document.querySelectorAll('iframe').length === 1 ? document.querySelector('iframe') : null);
    const primaryFrame = document.querySelector('#embedIframe');
    if (primaryFrame) {
      isolate(primaryFrame);
    } else if (video) {
      isolate(video.closest('.jwplayer, .video-js, .plyr') || video);
      if (!attached.has(video)) {
        attached.add(video);
        video.controls = true;
        video.setAttribute('playsinline', '');
        video.addEventListener('loadedmetadata', () => { report('ready'); tryPlay(video); });
        video.addEventListener('playing', () => report('playing'));
        video.addEventListener('error', () => report('video_error'));
        if (video.readyState > 0) report(video.paused ? 'ready' : 'playing');
        tryPlay(video);
      }
    } else if (frame) {
      isolate(frame);
    }
    const text = document.body.innerText.trim();
    if (/^403\s+Forbidden\b/i.test(text) && text.length < 300) report('forbidden');
  }
  function scheduleScan() {
    if (scheduled) return;
    scheduled = true;
    requestAnimationFrame(scan);
  }
  // Keep normal player buttons, but prevent navigation links, forms and popups.
  document.addEventListener('click', event => {
    const link = event.target.closest && event.target.closest('a[href]');
    if (link) event.preventDefault();
  }, true);
  document.addEventListener('submit', event => event.preventDefault(), true);
  window.open = () => null;
  window.addEventListener('message', event => {
    const command = event.data;
    if (!command || command.kairosWebPlayer !== token) return;
    if (typeof command.muted === 'boolean') muted = command.muted;
    for (const video of document.querySelectorAll('video')) {
      video.muted = muted;
      if (command.play === true) tryPlay(video);
    }
    for (const frame of document.querySelectorAll('iframe')) {
      try { frame.contentWindow.postMessage(command, '*'); } catch (_) {}
    }
  });
  new MutationObserver(scheduleScan).observe(document, {childList:true,subtree:true});
  document.addEventListener('DOMContentLoaded', scan);
  window.addEventListener('load', scan);
  scheduleScan();
})();
