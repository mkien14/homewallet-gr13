// CloudFront Function: associate with the S3 frontend viewer-request behavior.
// Keep /api and /api/* on their separate ALB behavior. Never map origin errors
// to index.html: doing so can turn backend 401/403/404 responses into HTML 200s.
function handler(event) {
  var request = event.request;

  if (request.method !== 'GET' && request.method !== 'HEAD') {
    return request;
  }

  // Explicit routes prevent missing JS/CSS and unknown URLs from returning HTML.
  // Query strings (including the OAuth code and state) are left intact.
  var routes = {
    '/': true,
    '/households': true,
    '/households/': true,
    '/upload': true,
    '/upload/': true,
    '/auth/callback': true,
    '/auth/callback/': true,
  };

  if (Object.prototype.hasOwnProperty.call(routes, request.uri)) {
    request.uri = '/index.html';
  }

  return request;
}
