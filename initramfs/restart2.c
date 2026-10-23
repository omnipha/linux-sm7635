#define NR_EXIT 93
#define NR_WRITE 64
#define NR_REBOOT 142

#define REBOOT_MAGIC1 0xfee1dead
#define REBOOT_MAGIC2 672274793
#define REBOOT_CMD_RESTART2 0xa1b2c3d4

static long syscall4(long nr, long a0, long a1, long a2, long a3)
{
	register long x8 __asm__("x8") = nr;
	register long x0 __asm__("x0") = a0;
	register long x1 __asm__("x1") = a1;
	register long x2 __asm__("x2") = a2;
	register long x3 __asm__("x3") = a3;

	__asm__ volatile("svc #0"
			 : "+r"(x0)
			 : "r"(x8), "r"(x1), "r"(x2), "r"(x3)
			 : "memory");
	return x0;
}

static int same(const char *a, const char *b)
{
	while (*a && *a == *b) {
		a++;
		b++;
	}
	return *a == *b;
}

static void usage(void)
{
	static const char message[] = "usage: restart2 bootloader|recovery\n";

	syscall4(NR_WRITE, 2, (long)message, sizeof(message) - 1, 0);
	syscall4(NR_EXIT, 64, 0, 0, 0);
}

void __attribute__((noreturn, used)) restart2_main(long *stack)
{
	long argc = stack[0];
	char **argv = (char **)(stack + 1);
	long rc;

	if (argc != 2 || !(same(argv[1], "bootloader") || same(argv[1], "recovery")))
		usage();
	rc = syscall4(NR_REBOOT, REBOOT_MAGIC1, REBOOT_MAGIC2,
		      REBOOT_CMD_RESTART2, (long)argv[1]);
	syscall4(NR_EXIT, rc < 0 ? -rc : 1, 0, 0, 0);
	for (;;)
		;
}

__asm__(".text\n"
	".global _start\n"
	".type _start,%function\n"
	"_start:\n"
	"\tmov x0, sp\n"
	"\tbl restart2_main\n");
