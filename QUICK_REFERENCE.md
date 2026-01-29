# Quick Reference: Optimized API Usage

## ⚡ Performance Optimizations Summary

### Before vs After
```
BEFORE (Sequential):
┌─────────────────────────────────────────────────────┐
│ GPT API │ Sub1 │ Sub2 │ Sub3 │ ... │ Sub10 │        
│   3s    │  2s  │  2s  │  2s  │ ... │  2s   │ = 23s
└─────────────────────────────────────────────────────┘

AFTER (Parallel + Cached):
┌──────────┬──────────────────────────────┐
│ GPT API  │ All 10 subs in parallel     │
│   3s     │         max(2s)             │ = 5s
│ (cached) │                              │
└──────────┴──────────────────────────────┘
```

## 🎯 Quick Start

### Basic Usage (Optimized Defaults)
```bash
curl -X POST "http://localhost:8000/subcategory_with_counts" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "input_prompt": "Analyze fire-related complaints..."
  }'
```

### Custom Tuning
```bash
curl -X POST "http://localhost:8000/subcategory_with_counts" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "input_prompt": "Your prompt here...",
    "max_subcategories": 10,
    "max_workers": 15,
    "enable_cache": true
  }'
```

## 📊 Parameter Guide

| Parameter | Default | Range | Impact |
|-----------|---------|-------|--------|
| `max_subcategories` | 15 | 5-30 | Higher = slower but more complete |
| `max_workers` | 10 | 1-20 | Higher = faster (if server can handle) |
| `enable_cache` | true | true/false | Cache = instant on repeated prompts |

## 🚀 Performance Targets

| Subcategories | Expected Time | With Cache |
|---------------|---------------|------------|
| 5 | ~4s | ~2s |
| 10 | ~5s | ~2s |
| 15 | ~6s | ~3s |
| 20 | ~8s | ~4s |

## 💡 Best Practices

1. ✅ **Enable caching** for production
2. ✅ **Start with 10 max_subcategories** and tune based on needs
3. ✅ **Use 10-15 workers** on most servers
4. ✅ **Monitor response times** and adjust
5. ⚠️ **Don't exceed 20 subcategories** unless necessary

## 🔍 Troubleshooting

### Too Slow?
- Reduce `max_subcategories` to 8-10
- Increase `max_workers` to 15
- Ensure caching is enabled

### Elasticsearch Errors?
- Reduce `max_workers` to 5
- Check ES connection pool size
- Monitor ES cluster health

### Inconsistent Results?
- Disable cache with `enable_cache: false`
- Clear cache by restarting server

## 📈 Monitoring

Check logs for:
```
✓ Using cached GPT response for prompt hash: 1a2b3c4d...
Processing 10 subcategories in parallel with 10 workers...
```

---
For full details, see `OPTIMIZATION_GUIDE.md`
