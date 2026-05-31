let currentJWT = "", currentPage = 1, isLoading = false, hasMoreItems = true, currentCategory = "All";
let selectedGift = {};

// ── TOAST ──
function showToast(msg, type = "success") {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.className = `show ${type}`;
  clearTimeout(t._timer);
  t._timer = setTimeout(() => { t.className = ''; }, 3000);
}

// ── LOAD BTN ──
document.getElementById('loadBtn').addEventListener('click', async () => {
  const jwt = document.getElementById('jwtInput').value.trim();
  const errorMsg = document.getElementById('errorMsg');
  const btn = document.getElementById('loadBtn');

  if (!jwt) {
    errorMsg.textContent = "⚠️ Please enter your JWT token first.";
    errorMsg.style.display = "block";
    return;
  }

  currentJWT = jwt; currentPage = 1; hasMoreItems = true; currentCategory = "All";
  document.getElementById('itemsGrid').innerHTML = '';
  errorMsg.style.display = "none";
  btn.textContent = "AUTHENTICATING..."; btn.disabled = true;

  await fetchAndRenderItems(true);
  btn.textContent = "LOAD GIFT STORE"; btn.disabled = false;
});

// ── FETCH & RENDER ──
async function fetchAndRenderItems(refreshCats = false) {
  if (isLoading || !hasMoreItems) return;
  isLoading = true;

  try {
    const response = await fetch('/api/get_store', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ jwt: currentJWT, page: currentPage, limit: 24, category: currentCategory })
    });
    const data = await response.json();

    if (data.success) {
      document.getElementById('loginBox').style.display = 'none';
      document.getElementById('storeBox').style.display = 'block';
      document.getElementById('giftsSent').textContent = `🎁 Sent Today: ${data.sent_today}`;

      if (data.wallet) {
        document.getElementById('valDiamond').textContent = `💎 ${data.wallet.diamond.toLocaleString()}`;
        document.getElementById('valGold').textContent = `🪙 ${data.wallet.gold.toLocaleString()}`;
        document.getElementById('valTopup').textContent = data.wallet.last_topup;
      }

      if (refreshCats) renderCategoryButtons(data.categories);
      renderItems(data.items);

      hasMoreItems = data.has_more;
      currentPage++;
    } else {
      showToast("❌ " + data.message, "fail");
      document.getElementById('errorMsg').textContent = data.message;
      document.getElementById('errorMsg').style.display = 'block';
    }
  } catch (err) {
    showToast("❌ Failed to connect to server.", "fail");
  }

  isLoading = false;
}

function renderItems(items) {
  const grid = document.getElementById('itemsGrid');
  const frag = document.createDocumentFragment();

  items.forEach(item => {
    let purePrice = item.price_str.match(/\d+/)[0];
    let cType = item.price_str.includes('💎') ? 'diamond' : 'gold';

    const div = document.createElement('div');
    div.className = 'card';
    div.innerHTML = `
      <div class="sort-badge">${item.category}</div>
      <div class="card-img-container">
        <img src="/api/image/${item.item_id}" class="card-img" loading="lazy" decoding="async">
      </div>
      <div class="price">${item.price_str}</div>
      <div class="expire">Expires:<br>${item.expire_date}</div>
      <button class="btn-send" onclick="openGiftModal('${item.commodity_id}','${purePrice}','${cType}')">SEND GIFT</button>
    `;
    frag.appendChild(div);
  });

  grid.appendChild(frag);
}

// ── CATEGORY ──
function renderCategoryButtons(categories) {
  const bar = document.getElementById('categoryBar');
  bar.innerHTML = '<button class="cat-btn active" data-cat="All">All Items</button>';

  categories.forEach(cat => {
    const btn = document.createElement('button');
    btn.className = 'cat-btn';
    btn.textContent = cat;
    btn.onclick = () => {
      document.querySelectorAll('.cat-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      currentCategory = cat; currentPage = 1; hasMoreItems = true;
      document.getElementById('itemsGrid').innerHTML = '';
      fetchAndRenderItems();
    };
    bar.appendChild(btn);
  });

  // "All" button click
  bar.querySelector('[data-cat="All"]').onclick = () => {
    document.querySelectorAll('.cat-btn').forEach(b => b.classList.remove('active'));
    bar.querySelector('[data-cat="All"]').classList.add('active');
    currentCategory = "All"; currentPage = 1; hasMoreItems = true;
    document.getElementById('itemsGrid').innerHTML = '';
    fetchAndRenderItems();
  };
}

// ── MODAL ──
function openGiftModal(id, price, type) {
  selectedGift = { id, price, type };
  document.getElementById('giftModal').style.display = 'flex';
  document.getElementById('targetUid').focus();
}

function closeModal() {
  document.getElementById('giftModal').style.display = 'none';
}

// close on backdrop click
document.getElementById('giftModal').addEventListener('click', function(e) {
  if (e.target === this) closeModal();
});

// ── SEND ──
document.getElementById('confirmSend').addEventListener('click', async () => {
  const rUid = document.getElementById('targetUid').value.trim();
  const msg = document.getElementById('giftMsg').value;
  const btn = document.getElementById('confirmSend');

  if (!rUid) { showToast("⚠️ Enter Receiver UID!", "fail"); return; }

  btn.disabled = true; btn.textContent = "SENDING...";

  try {
    const res = await fetch('/api/send_gift', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ jwt: currentJWT, receiver_uid: rUid, commodity_id: selectedGift.id, price: selectedGift.price, currency: selectedGift.type, message: msg })
    });
    const data = await res.json();

    if (data.success) {
      showToast("✅ " + data.message, "success");
      closeModal();
      currentPage = 1; hasMoreItems = true;
      document.getElementById('itemsGrid').innerHTML = '';
      fetchAndRenderItems();
    } else {
      showToast("❌ " + data.message, "fail");
    }
  } catch (e) {
    showToast("❌ Failed to send gift.", "fail");
  }

  btn.disabled = false; btn.textContent = "CONFIRM";
});

// ── ACCESS TO JWT ──
document.getElementById('getJwtBtn').addEventListener('click', async () => {
  const accessToken = document.getElementById('accessTokenInput').value.trim();
  const errorEl = document.getElementById('jwtErrorMsg');
  const resultBox = document.getElementById('jwtResultBox');
  const tokenText = document.getElementById('jwtTokenText');
  const btn = document.getElementById('getJwtBtn');

  errorEl.style.display = 'none';
  resultBox.style.display = 'none';

  if (!accessToken) {
    errorEl.textContent = '⚠️ Please enter your access token.';
    errorEl.style.display = 'block';
    return;
  }

  btn.textContent = 'LOADING...'; btn.disabled = true;

  try {
    const res = await fetch(`https://ff-jwt-gen-api.lovable.app/api/public/token?access_token=${encodeURIComponent(accessToken)}`);
    const data = await res.json();

    if (data.success && data.token) {
      tokenText.textContent = data.token;
      resultBox.style.display = 'block';
    } else {
      errorEl.textContent = '❌ Invalid token or request failed.';
      errorEl.style.display = 'block';
    }
  } catch (e) {
    errorEl.textContent = '❌ Network error. Try again.';
    errorEl.style.display = 'block';
  }

  btn.textContent = 'GET'; btn.disabled = false;
});

document.getElementById('copyJwtBtn').addEventListener('click', () => {
  const token = document.getElementById('jwtTokenText').textContent;
  navigator.clipboard.writeText(token).then(() => {
    const btn = document.getElementById('copyJwtBtn');
    btn.textContent = '✓ COPIED!';
    setTimeout(() => btn.textContent = '⎘ COPY TOKEN', 2000);
  });
});

// ── INFINITE SCROLL ──
window.addEventListener('scroll', () => {
  if ((window.innerHeight + window.scrollY) >= document.body.offsetHeight - 600) {
    fetchAndRenderItems();
  }
}, { passive: true });
    
