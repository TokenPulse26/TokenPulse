use once_cell::sync::Lazy;
use serde::{Deserialize, Serialize};
use serde_json::Value;

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct PricingEntry {
    pub model: String,
    pub provider: String,
    pub input_cost_per_million: f64,
    pub output_cost_per_million: f64,
    pub context_window: u64,
}

static PRICING_JSON: &str = include_str!("../pricing.json");

static BUNDLED_PRICING: Lazy<Vec<PricingEntry>> =
    Lazy::new(|| serde_json::from_str(PRICING_JSON).unwrap_or_default());

pub fn calculate_cost(
    model: &str,
    provider: Option<&str>,
    input_tokens: u32,
    output_tokens: u32,
) -> f64 {
    let pricing = &*BUNDLED_PRICING;
    let model_lower = model.to_lowercase();
    let provider_lower = provider.map(str::to_lowercase);

    let matches_provider = |entry: &PricingEntry| match provider_lower.as_deref() {
        Some(provider) => entry.provider.eq_ignore_ascii_case(provider),
        None => true,
    };

    let entry = pricing
        .iter()
        .find(|p| matches_provider(p) && model_lower == p.model.to_lowercase())
        .or_else(|| {
            pricing.iter().find(|p| {
                matches_provider(p)
                    && (model_lower.contains(&p.model.to_lowercase())
                        || p.model.to_lowercase().contains(&model_lower))
            })
        })
        .or_else(|| {
            pricing
                .iter()
                .find(|p| model_lower == p.model.to_lowercase())
        })
        .or_else(|| {
            pricing.iter().find(|p| {
                model_lower.contains(&p.model.to_lowercase())
                    || p.model.to_lowercase().contains(&model_lower)
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

/// Try DB pricing first, then fall back to bundled pricing.json
pub fn calculate_cost_with_db(
    conn: &rusqlite::Connection,
    model: &str,
    provider: Option<&str>,
    input_tokens: u32,
    output_tokens: u32,
) -> f64 {
    if let Ok(Some((input_per_million, output_per_million))) =
        crate::db::get_price_for_model(conn, model, provider)
    {
        let input_cost = (input_tokens as f64 / 1_000_000.0) * input_per_million;
        let output_cost = (output_tokens as f64 / 1_000_000.0) * output_per_million;
        return input_cost + output_cost;
    }
    // Fall back to bundled pricing
    calculate_cost(model, provider, input_tokens, output_tokens)
}

/// Parse the LiteLLM model_prices_and_context_window.json format.
/// That file is a JSON object where each key is a model name and the value
/// contains input_cost_per_token, output_cost_per_token, litellm_provider, max_tokens.
pub fn parse_litellm_json(json_str: &str) -> Vec<PricingEntry> {
    let json: Value = match serde_json::from_str(json_str) {
        Ok(v) => v,
        Err(_) => return vec![],
    };

    let map = match json.as_object() {
        Some(m) => m,
        None => return vec![],
    };

    let mut entries = Vec::new();
    for (model_name, model_data) in map {
        let input_cost = model_data
            .get("input_cost_per_token")
            .and_then(|v| v.as_f64());
        let output_cost = model_data
            .get("output_cost_per_token")
            .and_then(|v| v.as_f64());

        // Skip entries without pricing (e.g. embedding-only or image models).
        // Also reject NaN, infinity, negatives, and absurd values so a
        // compromised or malformed upstream file can't poison cost math.
        let (input, output) = match (input_cost, output_cost) {
            (Some(i), Some(o)) => (i, o),
            _ => continue,
        };
        if !input.is_finite() || !output.is_finite() {
            continue;
        }
        // $1000/token is several orders of magnitude above real pricing;
        // values above this are treated as malformed.
        if input < 0.0 || output < 0.0 || input > 1000.0 || output > 1000.0 {
            continue;
        }

        let provider = model_data
            .get("litellm_provider")
            .and_then(|v| v.as_str())
            .unwrap_or("unknown")
            .to_string();

        let context_window = model_data
            .get("max_tokens")
            .and_then(|v| v.as_u64())
            .or_else(|| model_data.get("max_input_tokens").and_then(|v| v.as_u64()))
            .unwrap_or(0);

        entries.push(PricingEntry {
            model: model_name.clone(),
            provider,
            input_cost_per_million: input * 1_000_000.0,
            output_cost_per_million: output * 1_000_000.0,
            context_window,
        });
    }
    entries
}
