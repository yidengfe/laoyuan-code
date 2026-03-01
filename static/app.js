async function request(url, options = {}) {
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.error || '请求失败');
  }
  return res.json();
}

function renderStats(stats) {
  const entries = [
    ['管理员数量', stats.users],
    ['启用用户', stats.active_users],
    ['商品数量', stats.products],
    ['总库存', stats.total_stock],
  ];
  document.getElementById('stats').innerHTML = entries
    .map(([k, v]) => `<article class="stat-card"><p>${k}</p><h3>${v}</h3></article>`)
    .join('');
}

function renderUsers(users) {
  document.getElementById('users-table').innerHTML = users
    .map((u) => `
      <tr>
        <td>${u.id}</td>
        <td>${u.username}</td>
        <td>${u.role}</td>
        <td>${u.status}</td>
        <td><button onclick="deleteUser(${u.id})">删除</button></td>
      </tr>
    `)
    .join('');
}

function renderProducts(products) {
  document.getElementById('products-table').innerHTML = products
    .map((p) => `
      <tr>
        <td>${p.id}</td>
        <td>${p.name}</td>
        <td>${p.category}</td>
        <td>${p.stock}</td>
        <td>¥${Number(p.price).toFixed(2)}</td>
        <td><button onclick="deleteProduct(${p.id})">删除</button></td>
      </tr>
    `)
    .join('');
}

async function loadAll() {
  renderStats(await request('/api/stats'));
  renderUsers(await request('/api/users'));
  renderProducts(await request('/api/products'));
}

async function deleteUser(id) {
  await request(`/api/users/${id}`, { method: 'DELETE' });
  await loadAll();
}

async function deleteProduct(id) {
  await request(`/api/products/${id}`, { method: 'DELETE' });
  await loadAll();
}

window.deleteUser = deleteUser;
window.deleteProduct = deleteProduct;

document.getElementById('user-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  await request('/api/users', {
    method: 'POST',
    body: JSON.stringify(Object.fromEntries(fd.entries())),
  });
  e.target.reset();
  await loadAll();
});

document.getElementById('product-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  await request('/api/products', {
    method: 'POST',
    body: JSON.stringify(Object.fromEntries(fd.entries())),
  });
  e.target.reset();
  await loadAll();
});

loadAll().catch((e) => alert(e.message));
