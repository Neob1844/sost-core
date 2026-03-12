#include "sost/checkpoints.h"
#include <cassert>
#include <cstdio>

void test_empty_checkpoints() {
    // With LAST_CHECKPOINT_HEIGHT = 0, nothing is checkpointed
    assert(!sost::is_checkpointed(0, "anything"));
    assert(!sost::is_checkpointed(1, "anything"));
    assert(!sost::is_checkpointed(100, "anything"));
    printf("PASS: test_empty_checkpoints\n");
}

void test_checkpoint_match() {
    // This test simulates what happens when checkpoints exist
    // Since CHECKPOINTS is empty and LAST_CHECKPOINT_HEIGHT=0,
    // is_checkpointed always returns false
    // When we add real checkpoints, this test should be updated
    assert(!sost::is_checkpointed(0, "fake_hash"));
    printf("PASS: test_checkpoint_match\n");
}

void test_above_checkpoint() {
    // Height above last checkpoint should never be checkpointed
    assert(!sost::is_checkpointed(1000, "any_hash"));
    assert(!sost::is_checkpointed(999999, "any_hash"));
    printf("PASS: test_above_checkpoint\n");
}

int main() {
    test_empty_checkpoints();
    test_checkpoint_match();
    test_above_checkpoint();
    printf("\nAll checkpoint tests PASSED\n");
    return 0;
}
