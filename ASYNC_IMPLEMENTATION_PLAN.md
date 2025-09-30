# Asynchronous Background Processing Implementation Plan

## Overview

This plan enhances the existing `live`, `batch`, and `lazy` modes with concurrent background processing capabilities instead of creating new modes. This approach maintains backward compatibility while significantly improving performance.

## Implementation Status

### Phase 1: Background Worker Infrastructure (Week 1-2)

**Goal**: Create the foundation for concurrent processing

- [x] Create `BackgroundWorkerPool` class
- [x] Create `ConcurrentResultProcessor` class
- [x] Add worker configuration options
- [x] Basic integration with existing modes
- [x] Create `proofy/_impl/io/background_workers.py`
- [x] Create `proofy/_impl/io/concurrent_processor.py`
- [x] Modify `proofy/_impl/config.py`
- [x] Modify `pytest-proofy/pytest_proofy/config.py`

### Phase 2: Enhanced Mode Processing (Week 3-4)

**Goal**: Integrate concurrent processing into existing modes

- [x] Enhance `ResultsHandler` with background processing
- [x] Implement concurrent result processing
- [x] Implement concurrent attachment uploads
- [x] Add proper error handling and retry logic
- [x] Modify `proofy/_impl/io/results_handler.py`
- [ ] Modify `proofy/_impl/io/artifact_uploader.py`

### Phase 3: Testing and Optimization (Week 5-6)

**Goal**: Comprehensive testing and performance optimization

- [x] Unit tests for background workers
- [x] Integration tests for all modes
- [ ] Performance benchmarks
- [ ] Memory usage optimization
- [x] Create `tests/test_background_workers.py`
- [x] Create `tests/test_concurrent_processing.py`
- [x] Create `tests/test_enhanced_results_handler.py`

## Enhanced Architecture for Existing Modes

### Concurrent Processing Strategy

#### Live Mode Enhancement

- [ ] **Result Creation**: Still synchronous (immediate feedback)
- [ ] **Result Updates**: Background processing for final status updates
- [ ] **Attachments**: Concurrent background uploads
- [ ] **Tracebacks**: Background processing

#### Batch Mode Enhancement

- [ ] **Result Collection**: Still synchronous (immediate collection)
- [ ] **Batch Processing**: Concurrent processing of multiple results
- [ ] **Attachments**: Concurrent uploads within batches
- [ ] **Batch Sending**: Parallel API calls for multiple results

#### Lazy Mode Enhancement

- [ ] **Result Collection**: Still synchronous (immediate collection)
- [ ] **Session End Processing**: Concurrent processing of all results
- [ ] **Attachments**: Concurrent uploads with worker pools
- [ ] **Memory Management**: Background cleanup of processed results

## Core Components

### Background Worker Pool

- [ ] Create `BackgroundWorkerPool` class with thread pool management
- [ ] Implement `WorkerConfig` dataclass for configuration
- [ ] Add thread-safe task submission methods
- [ ] Implement graceful shutdown functionality
- [ ] Add timeout and retry mechanisms

### Concurrent Result Processor

- [ ] Create `ConcurrentResultProcessor` class
- [ ] Implement `process_results_concurrently()` method
- [ ] Implement `upload_attachments_concurrently()` method
- [ ] Add error handling and result collection
- [ ] Implement progress tracking

### Enhanced Results Handler

- [ ] Add background worker integration to `ResultsHandler`
- [ ] Enhance `_store_result_live()` with background processing
- [ ] Enhance `_store_result_batch()` with concurrent batch processing
- [ ] Enhance `send_result_lazy()` with concurrent processing
- [ ] Add proper cleanup and shutdown handling

## Configuration Extensions

### Worker Configuration

- [ ] Add `WorkerConfig` dataclass
- [ ] Add `max_workers` setting (default: 4)
- [ ] Add `max_attachment_workers` setting (default: 8)
- [ ] Add `task_timeout` setting (default: 30.0)
- [ ] Add `shutdown_timeout` setting (default: 30.0)
- [ ] Add `retry_attempts` setting (default: 3)
- [ ] Add `retry_delay` setting (default: 1.0)

### Enhanced ProofyConfig

- [ ] Add `enable_background_processing` flag (default: False)
- [ ] Add `worker_config` field
- [x] ~~Add `concurrent_batch_processing` flag (default: True)~~ **REMOVED** - In batch mode, only attachments are processed concurrently
- [ ] Add `concurrent_attachment_uploads` flag (default: True)

### CLI Configuration

- [ ] Add `--proofy-enable-background` option
- [ ] Add `--proofy-max-workers` option
- [ ] Add `--proofy-max-attachment-workers` option
- [ ] Add `--proofy-concurrent-batch` option
- [ ] Update configuration resolution logic

## Implementation Details

### Background Worker Pool Implementation

```python
# proofy/_impl/io/background_workers.py
class BackgroundWorkerPool:
    """Thread pool for background processing of results and attachments"""

    def __init__(self, config: WorkerConfig):
        # Implementation details...

    def start(self) -> None:
        # Start background worker pools

    def submit_result_task(self, func: Callable, *args, **kwargs) -> Future:
        # Submit a result processing task

    def submit_attachment_task(self, func: Callable, *args, **kwargs) -> Future:
        # Submit an attachment upload task

    def shutdown(self, timeout: float = 30.0) -> None:
        # Shutdown worker pools gracefully
```

### Concurrent Result Processor Implementation

```python
# proofy/_impl/io/concurrent_processor.py
class ConcurrentResultProcessor:
    """Handles concurrent processing of multiple results and attachments"""

    def process_results_concurrently(self, results: List[TestResult]) -> Dict[str, Any]:
        # Process multiple results concurrently

    def upload_attachments_concurrently(self, result: TestResult) -> List[Future]:
        # Upload all attachments for a result concurrently
```

### Enhanced Results Handler Implementation

```python
# Enhanced proofy/_impl/io/results_handler.py
class ResultsHandler:
    """Enhanced results handler with concurrent background processing"""

    def __init__(self, *, client, mode, output_dir, project_id, worker_config=None):
        # Initialize with background processing components

    def _store_result_live(self, result: TestResult) -> None:
        # Enhanced live mode with background processing

    def _store_result_batch(self, result: TestResult) -> None:
        # Enhanced batch mode with concurrent processing

    def send_result_lazy(self) -> None:
        # Enhanced lazy mode with concurrent processing
```

## Testing Strategy

### Unit Tests

- [ ] Test `BackgroundWorkerPool` functionality
- [ ] Test `ConcurrentResultProcessor` methods
- [ ] Test enhanced `ResultsHandler` methods
- [ ] Test configuration resolution
- [ ] Test error handling and retry logic

### Integration Tests

- [ ] Test enhanced live mode with real API
- [ ] Test enhanced batch mode with large batches
- [ ] Test enhanced lazy mode with large test suites
- [ ] Test concurrent attachment uploads
- [ ] Test graceful shutdown scenarios

### Performance Tests

- [ ] Benchmark concurrent vs sequential processing
- [ ] Test memory usage with large test suites
- [ ] Test concurrent upload performance
- [ ] Test worker pool scaling
- [ ] Test timeout and retry mechanisms

## Usage Examples

### Enhanced Live Mode

```bash
# Live mode with background processing (default)
pytest --proofy-mode live --proofy-max-workers 4

# Live mode with more attachment workers
pytest --proofy-mode live --proofy-max-attachment-workers 16
```

### Enhanced Batch Mode

```bash
# Batch mode with concurrent processing
pytest --proofy-mode batch --proofy-concurrent-batch --proofy-batch-size 50

# Batch mode with custom worker configuration
pytest --proofy-mode batch --proofy-max-workers 8 --proofy-max-attachment-workers 12
```

### Enhanced Lazy Mode

```bash
# Lazy mode with background processing
pytest --proofy-mode lazy --proofy-max-workers 6

# Lazy mode with high concurrency for large test suites
pytest --proofy-mode lazy --proofy-max-workers 12 --proofy-max-attachment-workers 20
```

## Expected Performance Improvements

### Live Mode

- [ ] **Result updates**: Non-blocking background processing
- [ ] **Attachments**: 3-5x faster uploads with concurrent workers
- [ ] **Overall**: 20-30% faster test execution

### Batch Mode

- [ ] **Batch processing**: 2-3x faster with concurrent result processing
- [ ] **Attachments**: 4-6x faster with concurrent uploads
- [ ] **Overall**: 40-60% faster for large batches

### Lazy Mode

- [ ] **Session end processing**: 3-4x faster with concurrent processing
- [ ] **Attachments**: 5-8x faster with worker pools
- [ ] **Overall**: 50-70% faster for large test suites

## Backward Compatibility

- [ ] All existing modes work exactly as before when background processing is disabled
- [ ] Background processing is disabled by default but can be enabled with --proofy-boost
- [ ] No breaking changes to existing APIs or configurations
- [ ] Existing test suites continue to work without modification
- [ ] Maintain existing mode semantics and behavior

## Dependencies

### Required Python Libraries

- [ ] `concurrent.futures` (built-in)
- [ ] `threading` (built-in)
- [ ] `queue` (built-in)
- [ ] `dataclasses` (built-in)

### Optional Dependencies

- [ ] Consider adding `asyncio` support for future async/await implementation
- [ ] Consider adding `aiohttp` for async HTTP client support

## Risk Mitigation

### Technical Risks

- [ ] **Thread Safety**: Ensure all shared resources are thread-safe
- [ ] **Memory Leaks**: Implement proper cleanup and resource management
- [ ] **Deadlocks**: Avoid circular dependencies in worker pools
- [ ] **Resource Exhaustion**: Implement proper limits and timeouts

### Compatibility Risks

- [ ] **Backward Compatibility**: Maintain existing behavior when disabled
- [ ] **Configuration Conflicts**: Handle conflicts between old and new settings
- [ ] **Error Handling**: Ensure graceful degradation on failures

## Success Criteria

### Functional Requirements

- [ ] All existing modes work with enhanced performance
- [ ] Background processing can be enabled with --proofy-boost flag
- [ ] Concurrent processing works for results and attachments
- [ ] Proper error handling and retry mechanisms
- [ ] Graceful shutdown and cleanup

### Performance Requirements

- [ ] 20%+ improvement in test execution time for live mode
- [ ] 40%+ improvement in test execution time for batch mode
- [ ] 50%+ improvement in test execution time for lazy mode
- [ ] 3x+ improvement in attachment upload speed
- [ ] No significant increase in memory usage

### Quality Requirements

- [ ] 90%+ test coverage for new components
- [ ] All existing tests continue to pass
- [ ] No breaking changes to public APIs
- [ ] Comprehensive documentation updates
- [ ] Performance benchmarks and monitoring

## Notes

- This implementation maintains the exact same user experience while dramatically improving performance
- Users can enable background processing with --proofy-boost and configure worker counts
- The core mode behavior remains familiar and predictable
- All changes are additive and backward compatible
