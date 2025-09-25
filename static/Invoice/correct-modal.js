function fmtAmt(v){return 'R ' + ((parseFloat(v)||0).toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2}));}

let CM = { del: null, inv: null, evoso: null, agent: null };

function getSalesOrderIdFromUrl(){
	const parts = window.location.pathname.split('/');
	return parts[parts.length-1];
}

async function fetchSalesOrderHeader(){
	const id = getSalesOrderIdFromUrl();
	const res = await fetch(`/api/sales-order/${id}`);
	if(!res.ok) throw new Error('Failed to load sales order');
	return res.json();
}

async function loadAgents(){
	const res = await fetch('/api/correct-invoice/agents');
	const agents = await res.json();
	const sel = document.getElementById('cm-agent-select');
	sel.innerHTML = '<option value="">Select agent</option>' + agents.map(a=>`<option value="${a.id}">${a.name}</option>`).join('');
}

async function loadOldProdUnitsAndInvoices(){
	if(!CM.del) return;
	const res = await fetch(`/api/correct-invoice/old-prod-units-and-invoices/${encodeURIComponent(CM.del)}`);
	const data = await res.json();
	const oldProdUnits = data.old_prod_units || [];
	const invoices = data.invoices || [];
	
	const oldSel = document.getElementById('cm-old-prod');
	const opts = '<option value="">Select production unit</option>' + oldProdUnits.map(p=>`<option value="${p.id}">${p.name}</option>`).join('');
	oldSel.innerHTML = opts;
	
	// Show all invoices initially with no change status
	const it = document.getElementById('cm-prod-invoices');
	it.innerHTML = invoices.map(i=>`<tr><td>${i.InvoiceNo||i.invoiceno}</td><td>${i.InvoiceDate||i.invoicedate||''}</td><td>${fmtAmt(i.InvoiceNett||i.invoicenett)}</td><td>${i.Status||i.status||''}</td><td>-</td></tr>`).join('');
}

async function loadAllProdUnits(){
	const res = await fetch('/api/correct-invoice/all-prod-units');
	const allProdUnits = await res.json();
	const newSel = document.getElementById('cm-new-prod');
	const opts = '<option value="">Select production unit</option>' + allProdUnits.map(p=>`<option value="${p.id}">${p.name}</option>`).join('');
	newSel.innerHTML = opts;
}

async function loadAllDeliveryLines(){
	if(!CM.del) return;
	const res = await fetch(`/api/fetch_delivery_note_lines/${encodeURIComponent(CM.del)}`);
	const data = await res.json();
	const lines = data.lines || [];
	const tbody = document.getElementById('cm-prod-lines');
	tbody.innerHTML = lines.map(l=>`<tr><td>${l.dellineindex}</td><td>${l.productdescription}</td><td>${l.produnitname}</td><td>-</td></tr>`).join('');
}

async function updateDeliveryLinesDisplay(){
	const oldId = document.getElementById('cm-old-prod').value;
	if(!oldId) {
		await loadAllDeliveryLines();
		// Reset invoices to show all with no change status
		const res = await fetch(`/api/correct-invoice/old-prod-units-and-invoices/${encodeURIComponent(CM.del)}`);
		const data = await res.json();
		const invoices = data.invoices || [];
		const it = document.getElementById('cm-prod-invoices');
		it.innerHTML = invoices.map(i=>`<tr><td>${i.InvoiceNo||i.invoiceno}</td><td>${i.InvoiceDate||i.invoicedate||''}</td><td>${fmtAmt(i.InvoiceNett||i.invoicenett)}</td><td>${i.Status||i.status||''}</td><td>-</td></tr>`).join('');
		return;
	}
	
	// Get lines that will be edited
	const res = await fetch(`/api/correct-invoice/lines-and-invoices?del_note_no=${encodeURIComponent(CM.del)}&old_prod_unit_id=${encodeURIComponent(oldId)}`);
	const data = await res.json();
	const editLines = data.lines || [];
	const invoicesWithLines = data.invoices || [];
	
	// Get all lines
	const allRes = await fetch(`/api/fetch_delivery_note_lines/${encodeURIComponent(CM.del)}`);
	const allData = await allRes.json();
	const allLines = allData.lines || [];
	
	// Create map of lines that will be edited
	const editLineIds = new Set(editLines.map(l => l.DelLineIndex || l.dellineindex));
	
	const tbody = document.getElementById('cm-prod-lines');
	tbody.innerHTML = allLines.map(l=>{
		const willEdit = editLineIds.has(l.dellineindex);
		const indicator = willEdit ? '<span style="color: #dc2626; font-weight: bold;">Will be updated</span>' : '<span style="color: #059669;">No change</span>';
		return `<tr><td>${l.dellineindex}</td><td>${l.productdescription}</td><td>${l.produnitname}</td><td>${indicator}</td></tr>`;
	}).join('');
	
	// Get all invoices for the delivery note
	const allInvoicesRes = await fetch(`/api/correct-invoice/old-prod-units-and-invoices/${encodeURIComponent(CM.del)}`);
	const allInvoicesData = await allInvoicesRes.json();
	const allInvoices = allInvoicesData.invoices || [];
	
	// Create map of invoices that will be affected
	const affectedInvoiceIds = new Set();
	invoicesWithLines.forEach(inv => {
		const delLineIndex = inv.DelLineIndex;
		console.log(editLineIds, delLineIndex)
		if (editLineIds.has(delLineIndex)) {
			console.log("Added")
			affectedInvoiceIds.add(inv.InvoiceIndex);
		}
	});
	
	// Update invoices display with all invoices and change status
	const it = document.getElementById('cm-prod-invoices');
	it.innerHTML = allInvoices.map(i=>{
		const invoiceId = i.invoiceindex;
		const willChange = affectedInvoiceIds.has(invoiceId);
		console.log(invoiceId, affectedInvoiceIds, willChange)
		const changeStatus = willChange ? '<span style="color: #dc2626; font-weight: bold;">Will be affected</span>' : '<span style="color: #059669;">No change</span>';
		return `<tr><td>${i.InvoiceNo||i.invoiceno}</td><td>${i.InvoiceDate||i.invoicedate||''}</td><td>${fmtAmt(i.InvoiceNett||i.invoicenett)}</td><td>${i.Status||i.status||''}</td><td>${changeStatus}</td></tr>`;
	}).join('');
}


async function submitAgent(){
	const newAgent = document.getElementById('cm-agent-select').value;
	if(!CM.del || !newAgent) return;
	const res = await fetch('/api/correct-invoice/submit-agent-change',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({del_note_no:CM.del,new_agent_id:newAgent})});
	const j = await res.json();
	if(j.success) {
		alert('Agent updated successfully');
		window.location.reload();
	} else {
		alert('Failed: ' + (j.error||'Unknown error'));
	}
}

async function submitProd(){
	const oldId = document.getElementById('cm-old-prod').value;
	const newId = document.getElementById('cm-new-prod').value;
	if(!CM.del || !oldId || !newId) return;
	const res = await fetch('/api/correct-invoice/submit-produnit-change',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({del_note_no:CM.del,old_prod_unit_id:oldId,new_prod_unit_id:newId})});
	const j = await res.json();
	alert(j.success? 'Production unit updated successfully':'Failed: ' + (j.error||'Unknown error'));
}

function openModal(){
	document.getElementById('correct-modal').classList.remove('hidden');
}
function closeModal(){
	document.getElementById('correct-modal').classList.add('hidden');
}

window.addEventListener('DOMContentLoaded', async ()=>{
	// Read header to get the delivery note number
	try{
		const data = await fetchSalesOrderHeader();
		const header = data.sales_order_header || {};
		CM.del = header.invoicedelnoteno || header.InvoiceDelNoteNo || '';
		CM.inv = header.invoiceno || header.InvoiceNo || '';
		CM.evoso = header.invoiceevosonumber || header.InvoiceEvoSONumber || '';
		CM.agent = header.agentname || header.AgentName || '';
		document.getElementById('cm-delnote').textContent = CM.del;
		document.getElementById('cm-invoice').textContent = CM.inv;
		document.getElementById('cm-evoso').textContent = CM.evoso;
		const currentAgentInput = document.getElementById('cm-agent-current');
		if (currentAgentInput) currentAgentInput.value = CM.agent;
		await loadAgents();
		await loadOldProdUnitsAndInvoices();
		await loadAllProdUnits();
		// preload invoices list for agent step
		if (CM.del) {
			try {
				const res = await fetch(`/api/invoices-for-delivery-note/${encodeURIComponent(CM.del)}`);
				const invs = await res.json();
				document.getElementById('cm-agent-invoices').innerHTML = (invs||[]).map(i=>`<tr><td>${i.invoiceno||i.InvoiceNo}</td><td>${i.invoicedate||i.InvoiceDate||''}</td><td>${fmtAmt(i.invoicenett||i.InvoiceNett)}</td><td>${i.status||i.Status||''}</td></tr>`).join('');
			} catch(e) { console.error(e); }
		}
		// preload delivery lines for production unit step
		await loadAllDeliveryLines();
	}catch(e){
		console.error(e);
	}

	document.getElementById('open-correct-modal').addEventListener('click', openModal);
	document.getElementById('close-correct-modal').addEventListener('click', closeModal);

	// step selection
	document.getElementById('choose-agent').addEventListener('click', ()=>{
		document.getElementById('step-agent').classList.remove('hidden');
		document.getElementById('step-prod').classList.add('hidden');
		document.getElementById('choose-prod').classList.remove('active');
		document.getElementById('choose-agent').classList.add('active');
	});
	document.getElementById('choose-prod').addEventListener('click', ()=>{
		document.getElementById('step-prod').classList.remove('hidden');
		document.getElementById('step-agent').classList.add('hidden');
		document.getElementById('choose-prod').classList.add('active');
		document.getElementById('choose-agent').classList.remove('active');
	});

	// production unit dropdown change handler
	document.getElementById('cm-old-prod').addEventListener('change', updateDeliveryLinesDisplay);

	// actions
	document.getElementById('cm-agent-submit').addEventListener('click', submitAgent);
	document.getElementById('cm-prod-submit').addEventListener('click', submitProd);

	// Initialize Select2 on dropdowns once DOM and jQuery are available
	if (window.$ && $.fn && $.fn.select2) {
		$('#cm-agent-select').select2();
		$('#cm-old-prod').select2();
		$('#cm-new-prod').select2();
	}
});


