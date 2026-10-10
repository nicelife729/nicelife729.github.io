(function () {
  if (window.__postMetadataPlacementInitialized) return
  window.__postMetadataPlacementInitialized = true

  var media = window.matchMedia("(max-width: 44.984375em)")

  function placePostMetadata() {
    var post = document.querySelector(".md-content--post")
    if (!post) return

    var article = post.querySelector(":scope > .md-content__inner")
    var sidebar = post.querySelector(":scope > .md-sidebar--post")
    var metadata = post.querySelector(".md-post__meta")
    var heading = article && article.querySelector(":scope > h1")
    if (!article || !sidebar || !metadata || !heading) return

    if (!metadata.__postMetadataOrigin) {
      var origin = document.createComment("post-metadata-origin")
      metadata.before(origin)
      metadata.__postMetadataOrigin = origin
    }

    if (media.matches) {
      heading.after(metadata)
      metadata.classList.add("md-post__meta--inline")

      var remaining = sidebar.querySelector(
        ".md-post__meta, .md-post__authors, .md-nav--secondary"
      )
      sidebar.classList.toggle("md-sidebar--post--empty", !remaining)
      return
    }

    metadata.__postMetadataOrigin.after(metadata)
    metadata.classList.remove("md-post__meta--inline")
    sidebar.classList.remove("md-sidebar--post--empty")
  }

  placePostMetadata()

  if (typeof document$ !== "undefined") {
    document$.subscribe(placePostMetadata)
  } else if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", placePostMetadata)
  }

  if (media.addEventListener) {
    media.addEventListener("change", placePostMetadata)
  } else {
    media.addListener(placePostMetadata)
  }
})()
