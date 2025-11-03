(function () {
    var isProduct = /^\/product\//.test(window.location.pathname);
    document.body.classList.toggle('theme-product', isProduct);
})();