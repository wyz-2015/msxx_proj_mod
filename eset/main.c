#include "common.h"
#include "parser.h"
#include <argp.h>

typedef struct Args {
	char mode;
	char* outFilePath;
	char* inFilePath;
} Args;

static const struct argp_option options[] = {
	{ "compile", 'c', NULL, 0, "编译模式(暂不支持)" },
	{ "decompile", 'd', NULL, 0, "反编模式" },
	{ "outFilePath", 'o', "FILE", 0, "输出文件路径(若未指定则输出到stdout)" },
	{ "inFilePath", 'i', "FILE", 0, "传入文件路径" },
	{ 0 }
};

static error_t parse_opt(int key, char* arg, struct argp_state* state)
{
	Args* args = state->input;

	switch (key) {
	case 'c': {
		if (args->mode) {
			error(EINVAL, EINVAL, "-d -c能且只能指定一个");
		}
		args->mode = 'c';
		break;
	}
	case 'd': {
		if (args->mode) {
			error(EINVAL, EINVAL, "-d -c能且只能指定一个");
		}
		args->mode = 'd';
		break;
	}
	case 'o': {
		args->outFilePath = arg;
		break;
	}
	case 'i': {
		args->inFilePath = arg;
		break;
	}
	}
	return 0;
}

static struct argp argp = { options, parse_opt, NULL, "MSXX eset脚本<s>编译</s>、反编工具" };

int main(int argc, char** argv)
{
	Args args = {
		.mode = '\0',
		.inFilePath = NULL,
		.outFilePath = NULL
	};
	if (argc == 1) {
		argp_help(&argp, stdout, ARGP_HELP_USAGE | ARGP_HELP_LONG, NULL);
		error(EINVAL, EINVAL, "程序未接收到任何参数……");
	}

	argp_parse(&argp, argc, argv, 0, 0, &args);

	if (not args.inFilePath) {
		error(EINVAL, EINVAL, "必须指定传入文件");
	}

	FILE* outFile;
	if (args.mode == 'c') {
		if (not args.outFilePath) {
			error(EINVAL, EINVAL, "-c模式下需要指定输出文件");
		}
		outFile = fopen(args.outFilePath, "wb"); // wb+ ?
	} else if (args.mode == 'd') {
		if (args.outFilePath) {
			outFile = fopen(args.outFilePath, "wt");
		} else {
			outFile = stdout;
		}
	}
	if (not outFile) {
		error(ENOENT, ENOENT, "%s：无法打开文件：%s", __func__, argv[1]);
	}

	FILE* inFile = fopen(args.inFilePath, "rb");
	if (not inFile) {
		error(ENOENT, ENOENT, "%s：无法打开文件：%s", __func__, argv[1]);
	}

	switch (args.mode) {
	case 'd': {
		parser_main(inFile, outFile);
		break;
	}
	case 'c': {
		error(EINVAL, EINVAL, "-c模式暂不支持");
	}
	default: {
		error(EINVAL, EINVAL, "未知模式：%c", args.mode);
	}
	}

	fclose(inFile);
	if (outFile != NULL and outFile != stdout) {
		fclose(outFile);
	}
	return 0;
}
