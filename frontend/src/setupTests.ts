import { configure } from '@testing-library/react';

// findBy*/waitFor wait up to 5 s (default 1 s) so a loaded full parallel run does not fail
// with "Unable to find ..." before the element appears. Assertions are unchanged. See docs/TESTING.md.
configure({ asyncUtilTimeout: 5000 });
