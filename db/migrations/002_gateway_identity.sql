-- Optional upgrade of the original sample gateway name; custom mappings preserved.
BEGIN;
UPDATE devices SET iothub_device_id='pond-gateway-01'
WHERE device_id='LOBSTER_CAGE_VANPHONG_01' AND iothub_device_id='lobster-gateway-01';
COMMIT;
