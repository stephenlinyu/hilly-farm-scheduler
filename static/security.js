(() => {
  const originalFetch = window.fetch.bind(window);
  const unsafeMethods = new Set(["POST", "PUT", "PATCH", "DELETE"]);

  function readCookie(name) {
    const prefix = `${encodeURIComponent(name)}=`;
    for (const part of document.cookie.split(";")) {
      const value = part.trim();
      if (value.startsWith(prefix)) {
        return decodeURIComponent(value.slice(prefix.length));
      }
    }
    return "";
  }

  window.fetch = (input, init = {}) => {
    const requestMethod = String(
      init.method || (input instanceof Request ? input.method : "GET")
    ).toUpperCase();
    const requestUrl = new URL(
      input instanceof Request ? input.url : String(input),
      window.location.href
    );

    if (unsafeMethods.has(requestMethod) && requestUrl.origin === window.location.origin) {
      const csrfToken = readCookie("farm_csrf_token");
      if (csrfToken) {
        const headers = new Headers(
          init.headers || (input instanceof Request ? input.headers : undefined)
        );
        headers.set("X-CSRF-Token", csrfToken);
        init = { ...init, headers };
      }
    }

    if (input instanceof Request) {
      return originalFetch(new Request(input, init));
    }
    return originalFetch(input, init);
  };
})();

