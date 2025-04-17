from flask import Blueprint, render_template, request, redirect, url_for, session, jsonify
from db import create_db_connection, close_db_connection
import pypyodbc as odbc
from routes.db_functions import get_products

maintanance_bp = Blueprint('maintanance', __name__)

def fetch_data(cursor):
    # Execute multiple queries in one go
    cursor.execute("""
        SELECT * FROM ZZProduct;
        SELECT * FROM ZZProductType;
        SELECT * FROM ZZProductSize;
        SELECT * FROM ZZProductWeight;
        SELECT * FROM ZZProductBrand;
        Select * from ZZProductClass;
        Select OutputidTaxRate, OutputTaxRate from [dbo].[_uvMarketTaxRates]
    """)

    # Initialize an empty dictionary to store the results
    data = {
        "products": [],
        "types": [],
        "sizes": [],
        "weights": [],
        "brands": [],
        "class": [],
        "tax_rates": [],
    }

    # Fetch the first result set for ZZProduct
    data["products"] = cursor.fetchall()
    cursor.nextset()  # Move to the next result set

    # Fetch the second result set for ZZProductType
    data["types"] = cursor.fetchall()
    cursor.nextset()

    # Fetch the third result set for ZZProductSize
    data["sizes"] = cursor.fetchall()
    cursor.nextset()

    # Fetch the fourth result set for ZZProductWeight
    data["weights"] = cursor.fetchall()
    cursor.nextset()

    # Fetch the fifth result set for ZZProductBrand
    data["brands"] = cursor.fetchall()
    cursor.nextset()

    # fetch the sixth result set for ProductClass
    data["class"] = cursor.fetchall()
    cursor.nextset()

    # fetch the sixth result set for ProductClass
    data["tax_rates"] = cursor.fetchall()


    # Process data into structured JSON format
    result = {
        "products": [{"id": row[0], "code": row[1], "description": row[2]} for row in data["products"]],
        "types": [{"id": row[0], "code": row[1], "description": row[2]} for row in data["types"]],
        "sizes": [{"id": row[0], "code": row[1], "description": row[2]} for row in data["sizes"]],
        "weights": [{"id": row[0], "code": row[1], "description": row[2]} for row in data["weights"]],
        "brands": [{"id": row[0], "code": row[1], "description": row[2]} for row in data["brands"]],
        "class": [{"id": row[0], "code": row[1], "description": row[2]} for row in data["class"]],
        "tax_rates": [{"id": row[0], "code": row[1]} for row in data["tax_rates"]],
    }
    return result

@maintanance_bp.route('/create-product', methods=['GET'])
def render_create_product():
    return render_template('Maintanance/create_product.html')  # Ensure the path to your HTML is correct

@maintanance_bp.route('/fetch-product-data', methods=['GET'])
def fetch_product_data():
    conn = create_db_connection()
    cursor = conn.cursor()
    result = fetch_data(cursor)
    return jsonify(result)

@maintanance_bp.route('/create-product', methods=['POST'])
def create_product():
    # Connect to SQL Server
    conn = create_db_connection()
    cursor = conn.cursor()

    # Collect data from the form
    stock_item_code = request.form.get('generatedProductCode')
    product_code = request.form.get('productCode')
    type_code = request.form.get('typeCode')
    class_code = request.form.get('classCode')
    size_code = request.form.get('sizeCode')
    weight_code = request.form.get('weightCode')
    brand_code = request.form.get('brandCode')
    output_tax_rate = request.form.get('taxRate')

    print(output_tax_rate, stock_item_code, product_code, type_code)
    query = "SELECT InputidTaxRate FROM [dbo].[_uvTaxRates] WHERE OutputidTaxRate = ?"
    cursor.execute(query, (output_tax_rate,))
    input_tax_rate = cursor.fetchone()

    if not all([product_code, type_code, class_code, size_code, weight_code, brand_code]):
        print("Not all fields entered")
        return jsonify({"error": "All fields are required"}), 400

    # SQL Insert Query
    query = """
    INSERT INTO [dbo].[ZZProductStockItem] (ProductStockItemCode, ProductIndex, ProductClassIndex, ProductWeightIndex, 
    ProductSizeIndex, ProductTypeIndex, ProductBrandIndex,
    [ProductOutputidTaxRate], [ProductInputidTaxRate])
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    values = (stock_item_code, product_code, class_code, weight_code, size_code, type_code, brand_code,
              output_tax_rate, input_tax_rate[0])

    # try:

    cursor.execute(query, values)
    conn.commit()
    cursor.execute("EXEC [dbo].[SIGCreateEvoStockItem]")
    conn.commit()
    # except Exception as e:
    #     return jsonify({"error": str(e)}), 500

    # Retrieve updated product options
    try:
        product_options = get_products(cursor)
    finally:
        cursor.close()
        conn.close()

    # Return success message and updated product options
    return jsonify({
        "success": "Product created successfully",
        "productOptions": [{"value": row[0], "text": row[1]} for row in product_options]
    }), 200


@maintanance_bp.route('/add-item', methods=['POST'])
def add_item():
    try:
        data = request.get_json()

        field_type = data['fieldType']
        new_code = data['newCode']
        new_description = data['newDescription']
        
        conn = create_db_connection()
        cursor = conn.cursor()
        
        # Prepare your SQL based on the field_type
        if field_type == 'product':
            query = "INSERT INTO ZZProduct (ProductCode, ProductDescription) VALUES (?, ?)"
            id_query = "Select ProductIndex from ZZProduct Where ProductCode = ?"
        elif field_type == 'type':
            query = "INSERT INTO ZZProductType (ProductTypeCode, ProductTypeDescription) VALUES (?, ?)"
            id_query = "Select ProductTypeIndex from ZZProductType Where ProductTypeCode = ?"
        elif field_type == 'class':
            query = "INSERT INTO ZZProductClass(ProductClassCode, ProductClassDescription) VALUES (?, ?)"
            id_query = "Select ProductClassIndex from ZZProductClass Where ProductClassCode = ?"
        elif field_type == 'size':
            query = "INSERT INTO ZZProductSize(ProductSizeCode, ProductSizeDescription) VALUES (?, ?)"
            id_query = "Select ProductSizeIndex from ZZProductSize Where ProductSizeCode = ?"
        elif field_type == 'weight':
            query = "INSERT INTO ZZProductWeight(ProductWeightCode, ProductWeightDescription) VALUES (?, ?)"
            id_query = "Select ProductWeightIndex from ZZProductWeight Where ProductWeightCode = ?"
        elif field_type == 'brand':
            query = "INSERT INTO ZZProductBrand(ProductBrandCode, ProductBrandDescription) VALUES (?, ?)"
            id_query = "Select ProductBrandIndex from ZZProductBrand Where ProductBrandCode = ?"
        
        cursor.execute(query, (new_code, new_description))
        cursor.execute(id_query,(new_code,))
        item_id = cursor.fetchone()
        conn.commit()
        
        conn.close()
        data = [ field_type + "Code", field_type + "Description", [item_id[0], new_code, new_description],]
        return jsonify({'success': True, "message": "Item added successfully!", "data":data}), 201
    
    except odbc.IntegrityError as e:
        print(f"Error: {e}")
        return jsonify({'success': False, 'error': "Item Code already exists"})
    
    except odbc.ProgrammingError as e:
        print(f"Error: {e}")
        return jsonify({'success': False, 'error': "Code can't be more than 4 characters"})
    
    except Exception as e:
        print(f"Error: {e}")
        return jsonify({'success': False, 'error': str(e)})
