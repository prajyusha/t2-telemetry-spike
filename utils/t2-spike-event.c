#include <stdio.h>
#include <telemetry_busmessage_sender.h>

int main(void)
{
    t2_init("t2_spike");
    T2ERROR result = t2_event_s("SPIKE_EVENT", "spike-event-ok");
    printf("t2_event_s returned %d\n", (int)result);
    t2_uninit();
    return result == T2ERROR_SUCCESS ? 0 : 1;
}
