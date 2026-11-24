-- Smart Inventory & Billing: NEW tables only. The 5 master tables are NOT created or altered here.
-- Safe to re-run (IF NOT EXISTS). Generated from the SQLAlchemy models.
CREATE DATABASE IF NOT EXISTS smart_inventory_billing CHARACTER SET utf8mb4;
USE smart_inventory_billing;

CREATE TABLE IF NOT EXISTS `Users` (
	user_id INTEGER NOT NULL AUTO_INCREMENT, 
	employee_id INTEGER, 
	full_name VARCHAR(120) NOT NULL, 
	email VARCHAR(120) NOT NULL, 
	password_hash VARCHAR(255) NOT NULL, 
	`role` ENUM('Admin','Manager','Cashier','Inventory_Clerk') NOT NULL, 
	is_active_user BOOL, 
	last_login DATETIME, 
	created_at DATETIME, 
	PRIMARY KEY (user_id), 
	FOREIGN KEY(employee_id) REFERENCES `Employees` (employee_id), 
	UNIQUE (email)
);

CREATE TABLE IF NOT EXISTS `Stock_Transactions` (
	txn_id INTEGER NOT NULL AUTO_INCREMENT, 
	product_id INTEGER NOT NULL, 
	txn_type VARCHAR(30) NOT NULL, 
	ref_type VARCHAR(30), 
	ref_no VARCHAR(40), 
	qty_in INTEGER NOT NULL, 
	qty_out INTEGER NOT NULL, 
	balance INTEGER NOT NULL, 
	remarks VARCHAR(255), 
	created_by INTEGER, 
	created_at DATETIME, 
	PRIMARY KEY (txn_id), 
	FOREIGN KEY(product_id) REFERENCES `Products` (product_id), 
	FOREIGN KEY(created_by) REFERENCES `Users` (user_id)
);

CREATE TABLE IF NOT EXISTS `Stock_Adjustments` (
	adjustment_id INTEGER NOT NULL AUTO_INCREMENT, 
	adjustment_no VARCHAR(30) NOT NULL, 
	adjustment_type VARCHAR(30) NOT NULL, 
	remarks VARCHAR(255), 
	created_by INTEGER, 
	created_at DATETIME, 
	PRIMARY KEY (adjustment_id), 
	UNIQUE (adjustment_no), 
	FOREIGN KEY(created_by) REFERENCES `Users` (user_id)
);

CREATE TABLE IF NOT EXISTS `Stock_Adjustment_Items` (
	item_id INTEGER NOT NULL AUTO_INCREMENT, 
	adjustment_id INTEGER NOT NULL, 
	product_id INTEGER NOT NULL, 
	quantity INTEGER NOT NULL, 
	PRIMARY KEY (item_id), 
	FOREIGN KEY(adjustment_id) REFERENCES `Stock_Adjustments` (adjustment_id), 
	FOREIGN KEY(product_id) REFERENCES `Products` (product_id)
);

CREATE TABLE IF NOT EXISTS `Purchases` (
	purchase_id INTEGER NOT NULL AUTO_INCREMENT, 
	purchase_no VARCHAR(30) NOT NULL, 
	supplier_invoice_no VARCHAR(50), 
	supplier_id INTEGER NOT NULL, 
	purchase_date DATE NOT NULL, 
	subtotal NUMERIC(12, 2) NOT NULL, 
	gst_amount NUMERIC(12, 2) NOT NULL, 
	total NUMERIC(12, 2) NOT NULL, 
	status ENUM('Draft','Completed','Cancelled'), 
	idempotency_key VARCHAR(64), 
	created_by INTEGER, 
	created_at DATETIME, 
	PRIMARY KEY (purchase_id), 
	UNIQUE (purchase_no), 
	FOREIGN KEY(supplier_id) REFERENCES `Suppliers` (supplier_id), 
	UNIQUE (idempotency_key), 
	FOREIGN KEY(created_by) REFERENCES `Users` (user_id)
);

CREATE TABLE IF NOT EXISTS `Purchase_Items` (
	item_id INTEGER NOT NULL AUTO_INCREMENT, 
	purchase_id INTEGER NOT NULL, 
	product_id INTEGER NOT NULL, 
	quantity INTEGER NOT NULL, 
	unit_cost NUMERIC(12, 2) NOT NULL, 
	gst_rate NUMERIC(5, 2) NOT NULL, 
	gst_amount NUMERIC(12, 2) NOT NULL, 
	line_total NUMERIC(12, 2) NOT NULL, 
	PRIMARY KEY (item_id), 
	FOREIGN KEY(purchase_id) REFERENCES `Purchases` (purchase_id), 
	FOREIGN KEY(product_id) REFERENCES `Products` (product_id)
);

CREATE TABLE IF NOT EXISTS `Sales` (
	sale_id INTEGER NOT NULL AUTO_INCREMENT, 
	invoice_no VARCHAR(30) NOT NULL, 
	idempotency_key VARCHAR(64), 
	customer_id INTEGER, 
	sale_date DATETIME, 
	subtotal NUMERIC(12, 2) NOT NULL, 
	discount NUMERIC(12, 2) NOT NULL, 
	taxable_value NUMERIC(12, 2) NOT NULL, 
	cgst NUMERIC(12, 2) NOT NULL, 
	sgst NUMERIC(12, 2) NOT NULL, 
	igst NUMERIC(12, 2) NOT NULL, 
	gst_amount NUMERIC(12, 2) NOT NULL, 
	round_off NUMERIC(12, 2) NOT NULL, 
	total NUMERIC(12, 2) NOT NULL, 
	amount_paid NUMERIC(12, 2) NOT NULL, 
	balance_due NUMERIC(12, 2) NOT NULL, 
	status ENUM('Draft','Completed','Cancelled','Partially_Returned','Returned'), 
	created_by INTEGER, 
	PRIMARY KEY (sale_id), 
	UNIQUE (invoice_no), 
	UNIQUE (idempotency_key), 
	FOREIGN KEY(customer_id) REFERENCES `Customers` (customer_id), 
	FOREIGN KEY(created_by) REFERENCES `Users` (user_id)
);

CREATE TABLE IF NOT EXISTS `Sale_Items` (
	sale_item_id INTEGER NOT NULL AUTO_INCREMENT, 
	sale_id INTEGER NOT NULL, 
	product_id INTEGER NOT NULL, 
	quantity INTEGER NOT NULL, 
	unit_price NUMERIC(12, 2) NOT NULL, 
	cost_price NUMERIC(12, 2) NOT NULL, 
	discount NUMERIC(12, 2) NOT NULL, 
	taxable_value NUMERIC(12, 2) NOT NULL, 
	gst_rate NUMERIC(5, 2) NOT NULL, 
	gst_amount NUMERIC(12, 2) NOT NULL, 
	line_total NUMERIC(12, 2) NOT NULL, 
	returned_qty INTEGER NOT NULL, 
	PRIMARY KEY (sale_item_id), 
	FOREIGN KEY(sale_id) REFERENCES `Sales` (sale_id), 
	FOREIGN KEY(product_id) REFERENCES `Products` (product_id)
);

CREATE TABLE IF NOT EXISTS `Sale_Payments` (
	payment_id INTEGER NOT NULL AUTO_INCREMENT, 
	sale_id INTEGER NOT NULL, 
	method ENUM('Cash','UPI','Card','Bank_Transfer') NOT NULL, 
	amount NUMERIC(12, 2) NOT NULL, 
	reference VARCHAR(60), 
	paid_at DATETIME, 
	PRIMARY KEY (payment_id), 
	FOREIGN KEY(sale_id) REFERENCES `Sales` (sale_id)
);

CREATE TABLE IF NOT EXISTS `Returns` (
	return_id INTEGER NOT NULL AUTO_INCREMENT, 
	return_no VARCHAR(30) NOT NULL, 
	sale_id INTEGER NOT NULL, 
	reason VARCHAR(255), 
	refund_method ENUM('Cash','UPI','Card','Bank_Transfer','Store_Credit') NOT NULL, 
	refund_amount NUMERIC(12, 2) NOT NULL, 
	status ENUM('Pending','Approved','Rejected'), 
	created_by INTEGER, 
	created_at DATETIME, 
	PRIMARY KEY (return_id), 
	UNIQUE (return_no), 
	FOREIGN KEY(sale_id) REFERENCES `Sales` (sale_id), 
	FOREIGN KEY(created_by) REFERENCES `Users` (user_id)
);

CREATE TABLE IF NOT EXISTS `Return_Items` (
	return_item_id INTEGER NOT NULL AUTO_INCREMENT, 
	return_id INTEGER NOT NULL, 
	sale_item_id INTEGER NOT NULL, 
	product_id INTEGER NOT NULL, 
	quantity INTEGER NOT NULL, 
	item_condition ENUM('Resalable','Damaged') NOT NULL, 
	refund_amount NUMERIC(12, 2) NOT NULL, 
	taxable_refunded NUMERIC(12, 2) NOT NULL, 
	gst_refunded NUMERIC(12, 2) NOT NULL, 
	cost_value NUMERIC(12, 2) NOT NULL, 
	PRIMARY KEY (return_item_id), 
	FOREIGN KEY(return_id) REFERENCES `Returns` (return_id), 
	FOREIGN KEY(sale_item_id) REFERENCES `Sale_Items` (sale_item_id), 
	FOREIGN KEY(product_id) REFERENCES `Products` (product_id)
);

CREATE TABLE IF NOT EXISTS `Expenses` (
	expense_id INTEGER NOT NULL AUTO_INCREMENT, 
	category VARCHAR(60) NOT NULL, 
	amount NUMERIC(12, 2) NOT NULL, 
	expense_date DATE NOT NULL, 
	payment_method ENUM('Cash','UPI','Card','Bank_Transfer'), 
	description VARCHAR(255), 
	created_by INTEGER, 
	created_at DATETIME, 
	PRIMARY KEY (expense_id), 
	FOREIGN KEY(created_by) REFERENCES `Users` (user_id)
);

CREATE TABLE IF NOT EXISTS `Notifications` (
	notification_id INTEGER NOT NULL AUTO_INCREMENT, 
	message VARCHAR(255) NOT NULL, 
	level VARCHAR(10), 
	is_read BOOL, 
	created_at DATETIME, 
	PRIMARY KEY (notification_id)
);

CREATE TABLE IF NOT EXISTS `Audit_Logs` (
	log_id INTEGER NOT NULL AUTO_INCREMENT, 
	user_id INTEGER, 
	action VARCHAR(40) NOT NULL, 
	entity VARCHAR(40), 
	entity_id VARCHAR(40), 
	details VARCHAR(255), 
	created_at DATETIME, 
	PRIMARY KEY (log_id), 
	FOREIGN KEY(user_id) REFERENCES `Users` (user_id)
);

CREATE TABLE IF NOT EXISTS `Store_Settings` (
	setting_key VARCHAR(50) NOT NULL, 
	setting_value VARCHAR(500), 
	PRIMARY KEY (setting_key)
);
