#include "common.h"
#include "script_formatter.h"
#include <limits.h>

void parser_cond(FILE* restrict esetFile, Script_Formatter* restrict sf)
{
	// TODO
	// Script_Formatter_printf(sf, "[...]");
	// fputs("[...]", sf->outFile);
	fputc('[', sf->outFile);

	int16_t ps = -1;
	uint8_t stack[UCHAR_MAX], c;
	int ci; // 用于区分0xff与EOF
	memset(stack, 0, UCHAR_MAX);

	while (true) {
		ci = fgetc(esetFile);
		if (ci == EOF) {
			error(EIO, EIO, "文件过早结束(0x%lx)", ftell(esetFile));
		}
		c = (uint8_t)ci;

		if (c == 0xa0) {
			if (ps >= 0) {
				fprintf(sf->outFile, "num(0x%x)", stack[ps]);
			}
			break;
		}

		if (c < 0x99) {
			ps += 1;
			stack[ps] = c;
		} else if (0x99 <= c and c <= 0xa1) {
			if (ps < 1) {
				fprintf(sf->outFile, "num(0x%x)", stack[0]);
			} else {
				uint8_t c1 = stack[ps], c2 = stack[ps - 1];
				ps -= 2;

				fprintf(sf->outFile, "(num(0x%x) operator(0x%x) num(0x%x))", c1, c2, c);
			}
		}
	}

	fputc(']', sf->outFile);

	/*
	if (ftell(esetFile) % 2 == 1) {
		fseek(esetFile, 1, 1);
	}
	*/
}

void parser_unit(FILE* restrict esetFile, Script_Formatter* restrict sf)
{
	// TODO
}

void parser_core(FILE* restrict esetFile, Script_Formatter* restrict sf)
{
	off_t sentenceStartOffset = ftell(esetFile);

	uint8_t opCode, size;
	fread(&opCode, sizeof(uint8_t), 1, esetFile);
	fread(&size, sizeof(uint8_t), 1, esetFile);

	switch (opCode) {
	case 0x00: {
		uint16_t gate;
		fread(&gate, sizeof(uint16_t), 1, esetFile);
		Script_Formatter_printf(sf, "gate(0x%x)\n", gate);

		break;
	}
	case 0x01: {
		uint16_t gate, window;
		fread(&gate, sizeof(uint16_t), 1, esetFile);
		fread(&window, sizeof(uint16_t), 1, esetFile);
		Script_Formatter_printf(sf, "gate_lock_window(0x%x, 0x%x)\n", gate, window);

		break;
	}
	case 0x02: {
		uint16_t limit;
		fread(&limit, sizeof(uint16_t), 1, esetFile);
		Script_Formatter_printf(sf, "lock_limit(0x%x)\n", limit);

		break;
	}
	case 0x03: {
		// 未使用，AI推测为自动滚动，待验证 TODO
		Script_Formatter_printf(sf, "auto_scrolling()");

		break;
	}
	case 0x04: {
		// 未使用，AI推测为设活动窗口[window, 最大值]
		uint16_t window;
		fread(&window, sizeof(uint16_t), 1, esetFile);
		Script_Formatter_printf(sf, "window(0x%x)", window);

		break;
	}
	case 0x05: {
		// TODO
		int16_t gotoOffset;
		fread(&gotoOffset, sizeof(int16_t), 1, esetFile);

		Script_Formatter_printf(sf, "if_not(");
		parser_cond(esetFile, sf);
		fputs(")\n", sf->outFile);

		// Script_Formatter_printf(&sf,"{");
		Script_Formatter_indent_add(sf, 1);
		Script_Formatter_printf(sf, "goto(%d)\n", gotoOffset);
		Script_Formatter_indent_add(sf, -1);

		// fseek(esetFile, size - (sizeof(uint8_t) * 2 + sizeof(int16_t)), 1); // 跳过条件解析，暂时

		break;
	}
	case 0x06: {
		uint16_t frames;
		fread(&frames, sizeof(uint16_t), 1, esetFile);

		Script_Formatter_printf(sf, "wait_frames(0x%x)\n", frames);

		break;
	}
	case 0x07: {
		Script_Formatter_printf(sf, "counter_clear()\n");
		break;
	}
	case 0x08: {
		uint8_t group, flags;
		uint16_t x, y;
		uint16_t unitID;

		fread(&group, sizeof(uint8_t), 1, esetFile);
		fread(&flags, sizeof(uint8_t), 1, esetFile);
		fread(&x, sizeof(int16_t), 1, esetFile);
		fread(&y, sizeof(int16_t), 1, esetFile);
		fread(&unitID, sizeof(uint16_t), 1, esetFile);

		Script_Formatter_printf(sf, "spawn(0x%x, 0x%x, 0x%x, 0x%x, Unit_0x%x(", group, flags, x, y, unitID);

		uint16_t paramLen = (size - 10) / sizeof(uint16_t);
		if (paramLen) {
			uint16_t unitParams[paramLen];
			fread(unitParams, sizeof(uint16_t), paramLen, esetFile);

			for (uint16_t i = 0; i < paramLen - 1; i += 1) {
				fprintf(sf->outFile, "0x%x, ", unitParams[i]);
			}
			fprintf(sf->outFile, "0x%x))\n", unitParams[paramLen - 1]);
		} else {
			fputs("))\n", sf->outFile);
		}

		break;
	}
	case 0x09: {
		uint16_t bodyLen, group, clearScroll;
		fread(&bodyLen, sizeof(uint16_t), 1, esetFile);
		fread(&group, sizeof(uint16_t), 1, esetFile);
		fread(&clearScroll, sizeof(uint16_t), 1, esetFile);

		Script_Formatter_printf(sf, "spawn_sub(0x%x, 0x%x, 0x%x, ", bodyLen, group, clearScroll);

		parser_cond(esetFile, sf);
		fputs(", ", sf->outFile);
		parser_cond(esetFile, sf);
		fputs(") {\n", sf->outFile);
		// fseek(esetFile, size - (sizeof(uint16_t) * 3 + sizeof(uint8_t) * 2), 1); // 暂时跳过解析

		Script_Formatter_indent_add(sf, 1);

		uint8_t opCode_peek;
		while (ftell(esetFile) < sentenceStartOffset + bodyLen) {
			fread(&opCode_peek, sizeof(uint8_t), 1, esetFile);
			if (opCode_peek >= 0x80) {
				fseek(esetFile, sentenceStartOffset + bodyLen, 0);
				break;
			}
			ungetc(opCode_peek, esetFile);

			parser_core(esetFile, sf);
		}
		Script_Formatter_indent_add(sf, -1);
		Script_Formatter_printf(sf, "}\n");

		break;
	}
	case 0x0a: {
		Script_Formatter_printf(sf, "if(");

		parser_cond(esetFile, sf);
		// fseek(esetFile, size - (sizeof(uint8_t) * 2), 1); // 暂时跳过解析
		fputs(")\n", sf->outFile);

		Script_Formatter_indent_add(sf, 1);
		parser_core(esetFile, sf);
		Script_Formatter_indent_add(sf, -1);

		break;
	}
	case 0x0b: {
		uint16_t bodyLen;
		fread(&bodyLen, sizeof(uint16_t), 1, esetFile);

		Script_Formatter_printf(sf, "{\n");
		Script_Formatter_indent_add(sf, 1);

		while (ftell(esetFile) < sentenceStartOffset + bodyLen) {
			parser_core(esetFile, sf);
		}

		Script_Formatter_indent_add(sf, -1);
		Script_Formatter_printf(sf, "}\n");

		break;
	}
	case 0x0c: {
		uint16_t bodyLen;
		fread(&bodyLen, sizeof(uint16_t), 1, esetFile);

		Script_Formatter_printf(sf, "random_choice(\n");
		Script_Formatter_indent_add(sf, 1);

		while (ftell(esetFile) < sentenceStartOffset + bodyLen) {
			parser_core(esetFile, sf);
			Script_Formatter_printf(sf, ",\n");
		}

		Script_Formatter_indent_add(sf, -1);
		Script_Formatter_printf(sf, ")\n");

		break;
	}
	case 0x0d: {
		Script_Formatter_printf(sf, "counter_plus1()\n");
		break;
	}
	case 0x0e: {
		// TODO: unknown

		uint16_t a, b;
		uint8_t c, d;
		fread(&a, sizeof(uint16_t), 1, esetFile);
		fread(&b, sizeof(uint16_t), 1, esetFile);
		fread(&c, sizeof(uint8_t), 1, esetFile);
		fread(&d, sizeof(uint8_t), 1, esetFile);
		Script_Formatter_printf(sf, "scroll(0x%x, 0x%0x, 0x%x, 0x%x)", a, b, c, d);

		break;
	}
	case 0x0f: {
		// TODO: unknown
		uint16_t a, b;
		fread(&a, sizeof(uint16_t), 1, esetFile);
		fread(&b, sizeof(uint16_t), 1, esetFile);

		Script_Formatter_printf(sf, "set_pair(0x%x, 0x%x)", a, b);

		break;
	}
	default: {
		error(EINVAL, EINVAL, "暂不支持的opCode：0x%x。当前位置：0x%lx", opCode, ftell(esetFile));
	}
	}
}

void parser_main(FILE* restrict esetFile, FILE* restrict outFile)
{
	Script_Formatter sf;
	Script_Formatter_init(&sf, outFile);

	uint16_t varientOffset;
	fread(&varientOffset, sizeof(uint16_t), 1, esetFile);
	Script_Formatter_printf(&sf, "varientOffset(0x%x)\n", varientOffset);

	uint8_t opCode_peek;
	while ((opCode_peek = fgetc(esetFile)) != 0xff) {
		ungetc(opCode_peek, esetFile);
		parser_core(esetFile, &sf);
	}
}
