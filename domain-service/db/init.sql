CREATE TABLE suppliers (
    id SERIAL PRIMARY KEY,
    company_name VARCHAR(255) NOT NULL,
    contact_person VARCHAR(255),
    phone VARCHAR(20)
);

INSERT INTO suppliers (company_name, contact_person, phone) VALUES
('Company A', 'John Doe', '1234567890'),
('Company B', 'Jane Smith', '0987654321');
