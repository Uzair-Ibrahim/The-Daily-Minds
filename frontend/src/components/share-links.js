export function shareLinks(article) {
  let url; try { url = new URL(article.url); } catch { return null; }
  if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password || /^(localhost$|127\.|10\.|192\.168\.|172\.(1[6-9]|2[0-9]|3[01])\.|169\.254\.|\[)/.test(url.hostname)) return null;
  const text = article.title + '\n' + url.href;
  return {
    WhatsApp: 'https://wa.me/?' + new URLSearchParams({text}),
    X: 'https://twitter.com/intent/tweet?' + new URLSearchParams({text: article.title, url: url.href}),
    LinkedIn: 'https://www.linkedin.com/sharing/share-offsite/?' + new URLSearchParams({url: url.href}),
  };
}
