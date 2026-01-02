import {
  db,
  fetchWithOffline,
  generateNotification
} from '/main_static/offline/db.js?v=43';

// -----------------------------
// Run when page loads
// -----------------------------
document.addEventListener('DOMContentLoaded', async () => {
  if (navigator.onLine) {
    await syncIssues();
  }
});

// -----------------------------
// Run when connection returns
// -----------------------------
window.addEventListener('online', async () => {
  console.log('Back online');
  await syncIssues();
});

// -----------------------------
// Central sync logic
// -----------------------------
let isSyncing = false;

async function syncIssues() {
  if (isSyncing) {
    console.log("Sync already in progress, skipping");
    return;
  }

  isSyncing = true;

  try {
    await flushOutbox();
    await submitUnsyncedReturns();
    window.updateNotificationsCount();
    window.updatePendingIndicator();
  } catch (err) {
    console.warn('Sync failed:', err);
  } finally {
    isSyncing = false;
  }
}


document.addEventListener("DOMContentLoaded", async () => {
    if (navigator.onLine) {
        await fetchWarehouses();
        await fetchProjects();
        await fetchProducts();
        await fetchIncompleteIssues();
    }
});

async function fetchWarehouses(){
  await fetchWithOffline({
      url: '/inventory/fetch_warehouses',
      store: 'warehouses',
      transform: d => d.warehouses
  });
}

async function fetchProjects(){
  await fetchWithOffline({
    url: '/inventory/fetch_projects',
    method: 'POST',
    store: 'projects',
    transform: d => d.prod_projects
  });
}

export async function fetchProducts(){
  const products = await fetch(`/inventory/fetch_products`)
  .then(r => r.json())
  .then(d => d.products.map(p => ({
      product_link: p.product_link,
      whse: p.WhseCode,        // 👈 REQUIRED
      qty_in_whse: p.qty_in_whse,

      product_code: p.product_code,
      product_desc: p.product_desc,

      whse_link: p.WhseLink,
      whse_name: p.WhseName,

      stocking_uom_id: p.stocking_uom_id,
      stocking_uom_code: p.stocking_uom_code,
      purchase_uom_id: p.purchase_uom_id,
      purchase_uom_code: p.purchase_uom_code,
      uom_cat_id: p.uom_cat_id
  })));
  await db.products.bulkPut(products);
}

export async function fetchIncompleteIssues(){
  // --------------- Fetch issues --------------- //
  await fetchWithOffline({
    url: "/inventory/SDK/incomplete_issues",
    store: "serverIssues",
    transform: d => d.issues
  });
  await fetchWithOffline({
    url: "/inventory/SDK/incomplete_issue_lines",
    store: "serverIssueLines",
    transform: d => d.issue_lines
  });
}

export async function flushOutbox() {
  if (!navigator.onLine) return;

  const items = await db.outbox.orderBy("created_at").toArray();

  for (const item of items) {
    try {
      const res = await fetch(item.url, {
        method: item.method || "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(item.body)
      });

      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      const data = await res.json();
      console.log("Outbox item synced", item, data);
      if (!data.success && data.status !== "success") {
        console.log(data)
        throw new Error("Server rejected request");
      }
      console.log("Outbox item synced", item, data);
      // Update offline issue with server ID
      if (item.body?.client_issue_id && data.issue_id) {
        const clientIssueId = item.body.client_issue_id;
        
        // Find and update the offline issue
        const issue = await db.offlineIssues
          .where("client_issue_id")
          .equals(clientIssueId)
          .first();
        console.log("Mapping offline issue", clientIssueId, issue);
        if (issue) {
          await db.offlineIssues.update(issue.local_id, {
            server_issue_id: data.issue_id,
            status: "synced"
          });
          console.log(data.issue_lines, Array.isArray(data.issue_lines));
          if (issue && Array.isArray(data.issue_lines)) {

            await db.offlineIssues.update(issue.local_id, {
              server_issue_id: data.issue_id,
              status: "synced"
            });

            // Map server lines back to offline lines
            for (const serverLine of data.issue_lines) {

              const offlineLine = await db.offlineIssueLines
                .where("client_issue_id")
                .equals(clientIssueId)
                .and(l => l.product_link === serverLine.issue_product_link)
                .first();
              console.log("Mapping offline line", serverLine, offlineLine);
              if (!offlineLine) continue;

              await db.offlineIssueLines.update(offlineLine.id, {
                server_issue_line_id: serverLine.issue_line_id
              });
            }
          }
        }
        console.log("Checking for offline returns to submit", clientIssueId);
        // Find and update the offline issue
        const issueReturn = await db.offlineReturns
          .where("client_issue_id")
          .equals(clientIssueId)
          .first();
        console.log("Found offline return", issueReturn);
        if (issueReturn) {
          await db.offlineReturns.update(issueReturn.local_id, {
            issue_id: data.issue_id
          });
        }
        await generateNotification(issue.created_by_user_id, "Stock Issue Synced", `Your offline stock issue has been synced successfully.`, data.issue_id);
      }
      await db.outbox.delete(item.id);
      
    } catch (err) {
      await generateNotification(window.FERMESYNC.userId, "Outbox Sync Failed", `An item in your outbox could not be synced.`, null);
      console.warn("Outbox flush failed", item, err);
      await db.outbox.update(item.id, {
        retry_count: (item.retry_count || 0) + 1
      });
      break;
    }
  }
}

async function submitUnsyncedReturns() {
  if (!navigator.onLine) return;

  const queuedReturns = await db.offlineReturns
    .where("status")
    .equals("queued")
    .toArray();

  console.log("Processing queued returns", queuedReturns);
  if (!queuedReturns.length) return;

  for (const issueReturn of queuedReturns) {

    // 1️⃣ Resolve server issue ID
    let serverIssueId = issueReturn.issue_id;

    if (typeof serverIssueId !== "number") {
      if (issueReturn.server_issue_id) {
        serverIssueId = issueReturn.server_issue_id;
      } else if (issueReturn.client_issue_id) {
        const issue = await db.offlineIssues
          .where("client_issue_id")
          .equals(issueReturn.client_issue_id)
          .first();

        if (!issue?.server_issue_id) {
          console.warn("Return waiting for issue sync", issueReturn);
          continue;
        }

        serverIssueId = issue.server_issue_id;
      } else {
        console.warn("Return waiting for issue sync", issueReturn);
        continue;
      }
    }

    await db.offlineReturns.update(issueReturn.local_id, {
      issue_id: serverIssueId
    });

    // 2️⃣ Map return lines
    const mappedReturns = [];

    for (const line of issueReturn.returns) {
      let serverIssueLineId;

      if (line.is_client_id) {
        const offlineLine = await db.offlineIssueLines
          .where("client_issue_id")
          .equals(issueReturn.client_issue_id)
          .and(l => l.client_issue_line_id === line.line_id)
          .first();

        if (!offlineLine?.server_issue_line_id) {
          console.warn("Skipping return line – not synced yet", line);
          continue;
        }

        serverIssueLineId = offlineLine.server_issue_line_id;
      } else {
        serverIssueLineId = line.line_id;
      }

      mappedReturns.push({
        line_id: serverIssueLineId,
        qty_issued: line.qty_issued,
        qty_returned: line.qty_returned
      });
    }

    if (!mappedReturns.length) continue;

    // 3️⃣ Submit to server
    const res = await fetch("/inventory/process_return", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        issue_id: serverIssueId,
        returned_to: issueReturn.returned_to,
        created_at: issueReturn.created_at,
        returns: mappedReturns
      })
    });
    console.log(res)
    if (!res.ok) {
      generateNotification(issueReturn.created_by_user_id, "Return Sync Failed", `Your offline stock issue return could not be synced.`, serverIssueId);
      console.warn("Return submission failed", issueReturn);
      return;
    }

    console.log("Return submission response", res);

    // 4️⃣ Mark as synced
    await db.offlineReturns.update(issueReturn.local_id, {
      status: "synced"
    });
    generateNotification(issueReturn.created_by_user_id, "Return Synced", `Your offline stock issue return has been synced successfully.`, serverIssueId);
  }
}
