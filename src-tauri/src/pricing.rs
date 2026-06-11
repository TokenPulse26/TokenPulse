use once_cell::sync::Lazy;
use serde::{Deserialize, Serialize};
use serde_json::Value;

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct PricingEntry {
    pub model: String,
    pub provider: String,
    pub input_cost_per_million: f64,
    pub output_cost_per_million: f64,
    #[serde(default)]
    pub cache_read_cost_per_million: Option<f64>,
    #[serde(default)]
    pub cache_creation_cost_per_million: Option<f64>,
    pub context_window: u64,
}

/// Token counts for one request, as reported by the provider.
///
/// Provider semantics differ, and the difference is load-bearing for cost:
/// - OpenAI-style APIs report `prompt_tokens` INCLUSIVE of `cached_tokens`.
/// - Anthropic reports `input_tokens` EXCLUSIVE of both
///   `cache_read_input_tokens` and `cache_creation_input_tokens`.
#[derive(Debug, Clone, Copy, Default)]
pub struct UsageTokens {
    pub input_tokens: i64,
    pub output_tokens: i64,
    pub cached_tokens: i64,
    pub cache_creation_tokens: i64,
    pub reasoning_tokens: i64,
}

#[derive(Debug, Clone, Copy)]
pub struct CostBreakdown {
    pub cost_usd: f64,
    /// True when the model was priced by fuzzy name match, or a cache rate
    /// had to be approximated from the input rate instead of coming from
    /// real pricing data. Stored per-request so the UI can mark the value.
    pub estimated: bool,
}

/// Per-million-token rates used to price one request.
pub struct Rates {
    pub input: f64,
    pub output: f64,
    pub cache_read: Option<f64>,
    pub cache_creation: Option<f64>,
}

static PRICING_JSON: &str = include_str!("../pricing.json");

static BUNDLED_PRICING: Lazy<Vec<PricingEntry>> =
    Lazy::new(|| serde_json::from_str(PRICING_JSON).unwrap_or_default());

fn is_anthropic(provider: Option<&str>) -> bool {
    provider
        .map(|p| p.eq_ignore_ascii_case("anthropic"))
        .unwrap_or(false)
}

fn cost_from_rates(
    usage: &UsageTokens,
    rates: &Rates,
    provider: Option<&str>,
    fuzzy_match: bool,
) -> CostBreakdown {
    let anthropic = is_anthropic(provider);
    let mut estimated = fuzzy_match;

    // OpenAI-style providers count cached tokens inside prompt_tokens, so the
    // full-rate portion is the non-cached remainder. Anthropic reports cache
    // reads/writes separately from input_tokens.
    let billable_input = if anthropic {
        usage.input_tokens
    } else {
        (usage.input_tokens - usage.cached_tokens).max(0)
    };

    let cache_read_rate = match rates.cache_read {
        Some(r) => r,
        None => {
            if usage.cached_tokens > 0 {
                estimated = true;
            }
            // Anthropic cache reads are billed at 0.1x input; OpenAI-style
            // cached tokens are typically discounted ~50%.
            if anthropic {
                rates.input * 0.1
            } else {
                rates.input * 0.5
            }
        }
    };

    let cache_creation_rate = match rates.cache_creation {
        Some(r) => r,
        None => {
            if usage.cache_creation_tokens > 0 {
                estimated = true;
            }
            // Anthropic 5-minute cache writes are billed at 1.25x input.
            if anthropic {
                rates.input * 1.25
            } else {
                rates.input
            }
        }
    };

    let cost = (billable_input as f64 / 1_000_000.0) * rates.input
        + (usage.cached_tokens as f64 / 1_000_000.0) * cache_read_rate
        + (usage.cache_creation_tokens as f64 / 1_000_000.0) * cache_creation_rate
        + (usage.output_tokens as f64 / 1_000_000.0) * rates.output;

    // A zero-rate entry (local/free models) costs $0 no matter how it was
    // matched — an "estimated" flag would be noise.
    if rates.input == 0.0 && rates.output == 0.0 {
        estimated = false;
    }

    CostBreakdown {
        cost_usd: cost.max(0.0),
        estimated,
    }
}

/// Find a bundled pricing entry. Returns the entry and whether the match was
/// fuzzy (substring) rather than exact. Exact matches are always preferred —
/// provider-scoped first, then global — before any fuzzy fallback. Among
/// fuzzy candidates the longest entry name wins, so a hypothetical
/// "o1-pro-2026" matches an "o1-pro" entry over plain "o1".
fn find_bundled_entry(
    model: &str,
    provider: Option<&str>,
) -> Option<(&'static PricingEntry, bool)> {
    let pricing = &*BUNDLED_PRICING;
    let model_lower = model.to_lowercase();
    let provider_lower = provider.map(str::to_lowercase);

    let matches_provider = |entry: &PricingEntry| match provider_lower.as_deref() {
        Some(provider) => entry.provider.eq_ignore_ascii_case(provider),
        None => true,
    };

    if let Some(e) = pricing
        .iter()
        .find(|p| matches_provider(p) && model_lower == p.model.to_lowercase())
    {
        return Some((e, false));
    }
    if let Some(e) = pricing
        .iter()
        .find(|p| model_lower == p.model.to_lowercase())
    {
        return Some((e, false));
    }

    let fuzzy_candidates = |scoped: bool| {
        pricing
            .iter()
            .filter(|p| !scoped || matches_provider(p))
            .filter(|p| {
                let pm = p.model.to_lowercase();
                model_lower.contains(&pm) || pm.contains(&model_lower)
            })
            .max_by_key(|p| p.model.len())
    };

    if let Some(e) = fuzzy_candidates(true) {
        return Some((e, true));
    }
    if let Some(e) = fuzzy_candidates(false) {
        return Some((e, true));
    }
    None
}

/// Price a request from the bundled pricing table only.
pub fn calculate_cost(model: &str, provider: Option<&str>, usage: &UsageTokens) -> CostBreakdown {
    match find_bundled_entry(model, provider) {
        Some((e, fuzzy)) => cost_from_rates(
            usage,
            &Rates {
                input: e.input_cost_per_million,
                output: e.output_cost_per_million,
                cache_read: e.cache_read_cost_per_million,
                cache_creation: e.cache_creation_cost_per_million,
            },
            provider,
            fuzzy,
        ),
        None => CostBreakdown {
            cost_usd: 0.0,
            estimated: false,
        },
    }
}

/// Try DB pricing first (exact match, refreshed from LiteLLM), then fall back
/// to bundled pricing.json.
pub fn calculate_cost_with_db(
    conn: &rusqlite::Connection,
    model: &str,
    provider: Option<&str>,
    usage: &UsageTokens,
) -> CostBreakdown {
    if let Ok(Some(rates)) = crate::db::get_price_for_model(conn, model, provider) {
        return cost_from_rates(usage, &rates, provider, false);
    }
    calculate_cost(model, provider, usage)
}

/// Validate a cost-per-token value from an external pricing file.
fn sane_cost(v: f64) -> bool {
    // $1000/token is several orders of magnitude above real pricing;
    // values above this are treated as malformed.
    v.is_finite() && (0.0..=1000.0).contains(&v)
}

/// Parse the LiteLLM model_prices_and_context_window.json format.
/// That file is a JSON object where each key is a model name and the value
/// contains input_cost_per_token, output_cost_per_token, litellm_provider,
/// max_tokens, and (for caching providers) cache_read_input_token_cost /
/// cache_creation_input_token_cost.
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
        if !sane_cost(input) || !sane_cost(output) {
            continue;
        }

        let cache_read = model_data
            .get("cache_read_input_token_cost")
            .and_then(|v| v.as_f64())
            .filter(|v| sane_cost(*v))
            .map(|v| v * 1_000_000.0);
        let cache_creation = model_data
            .get("cache_creation_input_token_cost")
            .and_then(|v| v.as_f64())
            .filter(|v| sane_cost(*v))
            .map(|v| v * 1_000_000.0);

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
            cache_read_cost_per_million: cache_read,
            cache_creation_cost_per_million: cache_creation,
            context_window,
        });
    }
    entries
}

#[cfg(test)]
mod tests {
    use super::*;

    fn close(a: f64, b: f64) -> bool {
        (a - b).abs() < 1e-9
    }

    #[test]
    fn openai_cached_tokens_are_discounted_not_full_rate() {
        // gpt-4o bundled: $2.50/M input, $10.00/M output. prompt_tokens=10000
        // INCLUDES 8000 cached. Expected: 2000 @ 2.50 + 8000 @ 1.25 (50%
        // heuristic) + 1000 @ 10.00 = 0.005 + 0.01 + 0.01 = 0.025.
        let usage = UsageTokens {
            input_tokens: 10_000,
            output_tokens: 1_000,
            cached_tokens: 8_000,
            ..Default::default()
        };
        let c = calculate_cost("gpt-4o", Some("openai"), &usage);
        assert!(close(c.cost_usd, 0.025), "got {}", c.cost_usd);
        // Heuristic cache rate -> flagged estimated.
        assert!(c.estimated);
        // The old (broken) math billed all 10k input at full rate: 0.035.
        assert!(c.cost_usd < 0.035);
    }

    #[test]
    fn anthropic_cache_reads_and_writes_are_billed() {
        // claude-sonnet-4-6 bundled: $3/M input, $15/M output. Anthropic
        // input_tokens EXCLUDES cache tokens. Expected: 1000 @ 3.00 +
        // 10000 cache reads @ 0.30 (0.1x) + 2000 cache writes @ 3.75 (1.25x)
        // + 500 @ 15.00 = 0.003 + 0.003 + 0.0075 + 0.0075 = 0.021.
        let usage = UsageTokens {
            input_tokens: 1_000,
            output_tokens: 500,
            cached_tokens: 10_000,
            cache_creation_tokens: 2_000,
            ..Default::default()
        };
        let c = calculate_cost("claude-sonnet-4-6", Some("anthropic"), &usage);
        assert!(close(c.cost_usd, 0.021), "got {}", c.cost_usd);
        assert!(c.estimated, "heuristic cache rates must be flagged");
        // The old (broken) math priced cache traffic at $0: 0.0105.
        assert!(c.cost_usd > 0.0105);
    }

    #[test]
    fn exact_match_without_cache_is_not_estimated() {
        let usage = UsageTokens {
            input_tokens: 1_000,
            output_tokens: 500,
            ..Default::default()
        };
        let c = calculate_cost("gpt-4o", Some("openai"), &usage);
        assert!(close(c.cost_usd, 0.0075), "got {}", c.cost_usd);
        assert!(!c.estimated);
    }

    #[test]
    fn fuzzy_model_match_is_flagged_estimated() {
        // No "o1-pro" entry exists; substring fallback hits "o1". The cost is
        // a guess (real o1-pro pricing is 10x higher) so it must be flagged.
        let usage = UsageTokens {
            input_tokens: 1_000,
            output_tokens: 0,
            ..Default::default()
        };
        let c = calculate_cost("o1-pro", Some("openai"), &usage);
        assert!(c.cost_usd > 0.0);
        assert!(c.estimated);
    }

    #[test]
    fn free_local_models_are_never_flagged_estimated() {
        // "qwen2.5:0.5b" fuzzy-matches the bundled $0 "qwen2.5" ollama entry;
        // free is free, so the estimated flag must stay off.
        let usage = UsageTokens {
            input_tokens: 1_000,
            output_tokens: 500,
            ..Default::default()
        };
        let c = calculate_cost("qwen2.5:0.5b", Some("ollama"), &usage);
        assert!(close(c.cost_usd, 0.0));
        assert!(!c.estimated);
    }

    #[test]
    fn unknown_model_costs_zero_and_is_not_estimated() {
        let usage = UsageTokens {
            input_tokens: 1_000,
            output_tokens: 1_000,
            ..Default::default()
        };
        let c = calculate_cost("totally-unknown-model-xyz", Some("ollama"), &usage);
        assert!(close(c.cost_usd, 0.0));
        assert!(!c.estimated);
    }

    #[test]
    fn litellm_parse_extracts_cache_rates() {
        let json = r#"{
            "claude-sonnet-4-6": {
                "input_cost_per_token": 0.000003,
                "output_cost_per_token": 0.000015,
                "cache_read_input_token_cost": 0.0000003,
                "cache_creation_input_token_cost": 0.00000375,
                "litellm_provider": "anthropic",
                "max_tokens": 200000
            },
            "no-cache-model": {
                "input_cost_per_token": 0.000001,
                "output_cost_per_token": 0.000002,
                "litellm_provider": "openai",
                "max_tokens": 8192
            }
        }"#;
        let entries = parse_litellm_json(json);
        assert_eq!(entries.len(), 2);
        let claude = entries.iter().find(|e| e.model.contains("claude")).unwrap();
        assert!(close(claude.cache_read_cost_per_million.unwrap(), 0.3));
        assert!(close(claude.cache_creation_cost_per_million.unwrap(), 3.75));
        let plain = entries.iter().find(|e| e.model == "no-cache-model").unwrap();
        assert!(plain.cache_read_cost_per_million.is_none());
        assert!(plain.cache_creation_cost_per_million.is_none());
    }

    #[test]
    fn db_pricing_with_explicit_cache_rates_is_not_estimated() {
        let conn = crate::db::init_db(":memory:").unwrap();
        crate::db::upsert_pricing(
            &conn,
            "claude-test-model",
            "anthropic",
            3.0,
            15.0,
            Some(0.3),
            Some(3.75),
            200_000,
        )
        .unwrap();
        let usage = UsageTokens {
            input_tokens: 1_000,
            output_tokens: 500,
            cached_tokens: 10_000,
            cache_creation_tokens: 2_000,
            ..Default::default()
        };
        let c = calculate_cost_with_db(&conn, "claude-test-model", Some("anthropic"), &usage);
        assert!(close(c.cost_usd, 0.021), "got {}", c.cost_usd);
        assert!(!c.estimated, "explicit cache rates are real data, not estimates");
    }
}
