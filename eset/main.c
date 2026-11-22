#include "common.h"
#include "parser.h"

int main(int argc, char** argv)
{
	FILE* eset = fopen(argv[1], "rb");
	if (not eset) {
		error(ENOENT, ENOENT, "%s：无法打开文件：%s", __func__, argv[1]);
	}

	parser_main(eset, stdout);

	fclose(eset);
	return 0;
}
