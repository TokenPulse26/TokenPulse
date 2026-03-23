use serde::{Deserialize, Serialize};

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct PricingEntry {
    pub model: String,
    pub provider: String,
    pub input_cost_per_million: f64,
    pub output_cost_per_million: f64,
    pub context_window: u64,
}

static PRICING_JSON: &str = include_str!("../pricing.json");

pub fn load_pricing() -> Vec<PricingEntry> {
    serde_json::from_str(PRICING_JSON).unwrap_or_default()
}

pub fn calculate_cost(model: &str, input_tokens: u32, output_tokens: u32) -> f64 {
    let pricing = load_pricing();

    // Try exact match first, then prefix match
    let entry = pricing.iter().find(|p| {
        model.to_lowercase() == p.model.to_lowercase()
    }).or_else(|| {
        pricing.iter().find(|p| {
            model.to_lowercase().contains(&p.model.to_lowercase())
                || p.model.to_lowercase().contains(&model.to_lowercase())
        })
    });

    match entry {
        Some(e) => {
            let input_cost = (input_tokens as f64 / 1_000_000.0) * e.input_cost_per_million;
            let output_cost = (output_tokens as f64 / 1_000_000.0) * e.output_cost_per_million;
            input_cost + output_cost
        }
        None => 0.0,
    }
}

pub fn load_pricing_from_json(json: &str) -> Result<Vec<PricingEntry>, serde_json::Error> {
    serde_json::from_str(json)
}
