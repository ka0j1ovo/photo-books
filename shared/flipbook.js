const bookElement = document.querySelector("#book");
const pages = bookElement.querySelectorAll(".book-page");
const previousButton = document.querySelector("#previous");
const nextButton = document.querySelector("#next");
const pageStatus = document.querySelector("#page-status");
const orientationStatus = document.querySelector("#orientation");
const pageWidth = Number(bookElement.dataset.pageWidth) || 512;
const pageHeight = Number(bookElement.dataset.pageHeight) || 640;
document.documentElement.style.setProperty("--page-ratio", pageWidth / pageHeight);

/* 窄屏时按可用宽度缩小页面，单页模式不会被裁切。 */
const narrowScreen = window.matchMedia("(max-width: 700px)").matches;
const viewportWidth = document.documentElement.clientWidth || window.innerWidth;
const stageWidth = Math.max(240, viewportWidth - (narrowScreen ? 24 : 48));
const renderWidth = Math.min(pageWidth, Math.floor(stageWidth / (narrowScreen ? 1 : 2)));
const renderHeight = Math.round((renderWidth * pageHeight) / pageWidth);

const pageFlip = new St.PageFlip(bookElement, {
  width: renderWidth,
  height: renderHeight,
  size: "stretch",
  minWidth: Math.max(1, Math.round(renderWidth * 0.56)),
  maxWidth: renderWidth,
  minHeight: Math.max(1, Math.round(renderHeight * 0.56)),
  maxHeight: renderHeight,
  drawShadow: true,
  flippingTime: 760,
  usePortrait: true,
  startZIndex: 10,
  autoSize: true,
  maxShadowOpacity: 0.42,
  showCover: true,
  mobileScrollSupport: false,
  clickEventForward: true,
  useMouseEvents: true,
  swipeDistance: 24,
  showPageCorners: true,
  disableFlipByClick: false,
});

let currentPage = 0;
let isTurning = false;

/* 只加载当前页前后的几页，长书也不会一次拉完所有照片。 */
function loadPage(page) {
  page.querySelectorAll("img[data-src]").forEach((image) => {
    image.addEventListener("load", () => image.classList.add("is-loaded"), { once: true });
    image.src = image.dataset.src;
    image.removeAttribute("data-src");
    if (image.complete) image.classList.add("is-loaded");
  });
}

function ensurePages(center, behind = 2, ahead = 4) {
  const from = Math.max(0, center - behind);
  const to = Math.min(pages.length - 1, center + ahead);
  for (let i = from; i <= to; i += 1) {
    if (!pages[i].dataset.loaded) {
      pages[i].dataset.loaded = "1";
      loadPage(pages[i]);
    }
  }
}

function updateControls() {
  const pageCount = pageFlip.getPageCount();
  const lastPage = pageCount - 1;
  bookElement.dataset.edge = currentPage === 0 ? "front" : currentPage === lastPage ? "back" : "inside";

  previousButton.disabled = currentPage === 0 || isTurning;
  nextButton.disabled = currentPage === lastPage || isTurning;

  if (currentPage === 0) {
    pageStatus.textContent = "封面";
  } else if (currentPage === lastPage) {
    pageStatus.textContent = "封底";
  } else {
    pageStatus.textContent = `${String(currentPage + 1).padStart(2, "0")} / ${String(pageCount).padStart(2, "0")}`;
  }
}

pageFlip.on("flip", (event) => {
  currentPage = Number(event.data);
  ensurePages(currentPage);
  updateControls();
});

pageFlip.on("changeState", (event) => {
  isTurning = event.data !== "read";
  updateControls();
});

function updateOrientation(orientation) {
  bookElement.dataset.layout = orientation;
  orientationStatus.textContent = orientation === "portrait" ? "单页" : "双页展开";
}

pageFlip.on("init", (event) => updateOrientation(event.data.mode));
pageFlip.on("changeOrientation", (event) => updateOrientation(event.data));

pageFlip.loadFromHTML(pages);
ensurePages(0, 0, 4);
updateControls();

const requestedPage = Number(new URLSearchParams(location.search).get("page"));
if (Number.isInteger(requestedPage) && requestedPage >= 0 && requestedPage < pages.length) {
  ensurePages(requestedPage);
  pageFlip.turnToPage(requestedPage);
}

previousButton.addEventListener("click", () => {
  if (!isTurning) pageFlip.flipPrev("bottom");
});

nextButton.addEventListener("click", () => {
  if (!isTurning) pageFlip.flipNext("bottom");
});

window.addEventListener("keydown", (event) => {
  if (event.altKey || event.ctrlKey || event.metaKey || isTurning) return;

  if (event.key === "ArrowLeft") {
    event.preventDefault();
    pageFlip.flipPrev("bottom");
  }

  if (event.key === "ArrowRight" || event.key === " ") {
    event.preventDefault();
    pageFlip.flipNext("bottom");
  }

  if (event.key === "Home") pageFlip.turnToPage(0);
  if (event.key === "End") pageFlip.turnToPage(pageFlip.getPageCount() - 1);
});

/* 图片不做右击「图片另存为」、拖拽保存，也不长按弹出保存菜单。 */
bookElement.addEventListener("contextmenu", (event) => event.preventDefault());
document.addEventListener("dragstart", (event) => {
  if (event.target instanceof HTMLImageElement) event.preventDefault();
});
document.addEventListener("selectstart", (event) => {
  if (bookElement.contains(event.target)) event.preventDefault();
});
