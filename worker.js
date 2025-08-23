// Cloudflare Worker for R2 static site hosting
// Deploy this as a Worker and route it to lee.app.nz

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    
    // Handle directory paths by adding index.html
    let key = url.pathname.slice(1);
    
    if (!key) {
      key = 'index.html';
    } else if (key.endsWith('/')) {
      key += 'index.html';
    }
    
    // Try to fetch from R2
    const object = await env.BUCKET.get(key);
    
    if (object === null) {
      // Try with .html extension
      const htmlObject = await env.BUCKET.get(key + '.html');
      if (htmlObject !== null) {
        return new Response(htmlObject.body, {
          headers: {
            'content-type': 'text/html;charset=UTF-8',
          },
        });
      }
      
      // Return 404
      return new Response('Not Found', { status: 404 });
    }
    
    // Set appropriate content-type
    const headers = new Headers();
    object.writeHttpMetadata(headers);
    headers.set('etag', object.httpEtag);
    
    // Guess content-type if not set
    if (!headers.get('content-type')) {
      if (key.endsWith('.html')) headers.set('content-type', 'text/html;charset=UTF-8');
      else if (key.endsWith('.css')) headers.set('content-type', 'text/css');
      else if (key.endsWith('.js')) headers.set('content-type', 'application/javascript');
      else if (key.endsWith('.json')) headers.set('content-type', 'application/json');
      else if (key.endsWith('.png')) headers.set('content-type', 'image/png');
      else if (key.endsWith('.jpg') || key.endsWith('.jpeg')) headers.set('content-type', 'image/jpeg');
      else if (key.endsWith('.webp')) headers.set('content-type', 'image/webp');
      else if (key.endsWith('.svg')) headers.set('content-type', 'image/svg+xml');
    }
    
    return new Response(object.body, {
      headers,
    });
  },
};
