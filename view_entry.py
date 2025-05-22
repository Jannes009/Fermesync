import json

@frappe.whitelist()
def update_line_quantities(quantities):
    try:
        quantities = json.loads(quantities)
        doc = frappe.get_doc("Bill Of Lading", frappe.form_dict.name)
        
        # Validate total quantity
        total_qty = sum(quantities.values())
        if total_qty != doc.total_quantity:
            frappe.throw(f"Total quantity must equal {doc.total_quantity} bags")
        
        # Update each line
        for line_id, new_qty in quantities.items():
            line = next((l for l in doc.delivery_note_lines if str(l.idx) == line_id), None)
            if not line:
                frappe.throw(f"Line {line_id} not found")
            
            # Validate minimum quantity
            min_qty = line.sold_quantity + line.invoiced_quantity
            if new_qty < min_qty:
                frappe.throw(f"Quantity for line {line_id} cannot be less than {min_qty} bags")
            
            line.quantity = new_qty
        
        doc.save()
        frappe.db.commit()
        
        return {"success": True}
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Error updating line quantities")
        return {"success": False, "message": str(e)} 