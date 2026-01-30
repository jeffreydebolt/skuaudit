-- Supabase schema for SKUaudit benchmark data
-- Run this in your Supabase SQL editor

CREATE TABLE benchmark_data (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    price_tier TEXT NOT NULL,  -- under_15, 15_to_25, 25_to_50, 50_to_100, over_100
    fulfillment_pct DECIMAL(5,2) NOT NULL,
    cogs_pct DECIMAL(5,2) NOT NULL,
    margin_pct DECIMAL(5,2) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Index for querying by price tier
CREATE INDEX idx_benchmark_price_tier ON benchmark_data(price_tier);

-- Index for time-based queries (tracking trends)
CREATE INDEX idx_benchmark_created_at ON benchmark_data(created_at);

-- No RLS needed - this is anonymous aggregate data
-- But enable it anyway for good practice
ALTER TABLE benchmark_data ENABLE ROW LEVEL SECURITY;

-- Allow anonymous inserts (from the app)
CREATE POLICY "Allow anonymous inserts" ON benchmark_data
    FOR INSERT TO anon
    WITH CHECK (true);

-- Allow authenticated reads (for your analysis)
CREATE POLICY "Allow authenticated reads" ON benchmark_data
    FOR SELECT TO authenticated
    USING (true);

-- Useful queries for monitoring:

-- Total SKUs in database
-- SELECT COUNT(*) FROM benchmark_data;

-- SKUs by price tier
-- SELECT price_tier, COUNT(*) FROM benchmark_data GROUP BY price_tier;

-- Average margins by price tier
-- SELECT price_tier, AVG(margin_pct) as avg_margin FROM benchmark_data GROUP BY price_tier;

-- Daily submission count (for tracking growth)
-- SELECT DATE(created_at), COUNT(*) FROM benchmark_data GROUP BY DATE(created_at) ORDER BY DATE(created_at) DESC;


-- ============================================
-- Leads table for email capture (v2)
-- ============================================

CREATE TABLE leads (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    email TEXT NOT NULL,
    first_name TEXT,
    brand_name TEXT,
    sku_count INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_leads_email ON leads(email);
CREATE INDEX idx_leads_created_at ON leads(created_at);

ALTER TABLE leads ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Allow anonymous inserts" ON leads
    FOR INSERT TO anon
    WITH CHECK (true);

CREATE POLICY "Allow authenticated reads" ON leads
    FOR SELECT TO authenticated
    USING (true);
