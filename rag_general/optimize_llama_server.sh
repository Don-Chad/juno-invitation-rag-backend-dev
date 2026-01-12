#!/bin/bash
# Optimal llama-server configuration for single request latency

echo "=== Llama Server Optimization Guide for Single Request Latency ==="
echo ""
echo "Current performance: ~92ms average (good!)"
echo "Target: <50ms for single requests"
echo ""

# Check if llama-server is running
if pgrep -f "llama-server" > /dev/null; then
    echo "⚠️  llama-server is currently running. Stop it first:"
    echo "   pkill -f llama-server"
    echo ""
fi

echo "### Recommended llama-server startup command:"
echo ""
cat << 'EOF'
llama-server \
    --model /path/to/your/embedding-model.gguf \
    --port 7777 \
    --embedding \
    --threads 8 \
    --threads-batch 8 \
    --ctx-size 2048 \
    --batch-size 512 \
    --ubatch-size 512 \
    --n-gpu-layers 99 \
    --no-mmap \
    --cont-batching \
    --flash-attn \
    --cache-type-k f16 \
    --cache-type-v f16 \
    --log-disable
EOF

echo ""
echo "### Key optimizations explained:"
echo ""
echo "1. --threads 8: Use 8 CPU threads (adjust based on your CPU cores)"
echo "2. --threads-batch 8: Batch processing threads"
echo "3. --ctx-size 2048: Smaller context for embeddings (reduces memory)"
echo "4. --batch-size 512: Optimal for single requests"
echo "5. --ubatch-size 512: Unified batch size"
echo "6. --n-gpu-layers 99: Offload all layers to GPU (if available)"
echo "7. --no-mmap: Disable memory mapping for lower latency"
echo "8. --cont-batching: Continuous batching for better throughput"
echo "9. --flash-attn: Use flash attention (if supported)"
echo "10. --cache-type-k/v f16: Use FP16 for KV cache"
echo "11. --log-disable: Disable logging for performance"

echo ""
echo "### Additional system-level optimizations:"
echo ""

# CPU Governor
echo "1. Set CPU governor to performance mode:"
echo "   sudo cpupower frequency-set -g performance"
current_governor=$(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor 2>/dev/null || echo "unknown")
echo "   Current governor: $current_governor"

# NUMA
echo ""
echo "2. For NUMA systems, bind to specific node:"
echo "   numactl --cpunodebind=0 --membind=0 llama-server ..."

# Nice priority
echo ""
echo "3. Run with high priority:"
echo "   sudo nice -n -10 llama-server ..."

# GPU optimizations
echo ""
echo "4. For NVIDIA GPUs:"
echo "   - Set persistence mode: sudo nvidia-smi -pm 1"
echo "   - Set max performance: sudo nvidia-smi -pl 300"
echo "   - Lock GPU clocks: sudo nvidia-smi -lgc 1980"

echo ""
echo "### Environment variables for better performance:"
echo ""
echo "export OMP_NUM_THREADS=8"
echo "export CUDA_LAUNCH_BLOCKING=0"
echo "export CUDA_DEVICE_ORDER=PCI_BUS_ID"

echo ""
echo "### Test configuration:"
echo ""
echo "After starting the server with optimizations, test with:"
echo "curl -X POST http://localhost:7777/embedding \\"
echo "  -H 'Content-Type: application/json' \\"
echo "  -d '{\"content\": \"Test embedding generation speed\", \"embedding\": true}'"

echo ""
echo "### Monitoring script:"
echo "python monitor_embedding_performance.py" 