# Synthetic sample

`transactions.json` is hand-generated transaction-shaped data. All `demo-*`
addresses are intentionally not Bitcoin addresses. Transaction IDs are invented
sequential 64-character hex strings, not records collected from the chain.
There is no customer, sanctions, attribution, wallet, or investigative dataset.

Start the app and click **Try a sample**:

1. `demo-root` has four eligible outputs. Only Alice, Bob, and Carol appear:
   the initial limit is **3**.
2. Click `demo-alice`. It has three eligible outputs, but only Dana and Erin
   appear: the expansion limit is **2**.
3. Alice is now marked expanded. It cannot reveal its omitted third output.
4. Click Dana to see a cycle back to the root plus Ivan. The root remains one node.
5. Click Erin to see the empty-result message.

The offline tests use this file to verify the same behavior. No live service is
called in sample mode or by the test suite.
